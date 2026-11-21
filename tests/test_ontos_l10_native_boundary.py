"""Cross-language, separate native process: OS boundary, signed DFX receipt."""
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_v67_dfx import StaticShell, PartitionProposal, check_equivalence, make_approval
from omega_x_evolution.ontos_l10_release import issue_release
from omega_x_evolution.ontos_v55_scm import BinaryIVSCM, ResponseType
from omega_x_evolution.ontos_v65_hypertraces import Event
from fractions import Fraction as F
from omega_x_evolution.ontos_v66_wire import Envelope, encode

ROOT=Path(__file__).resolve().parents[1]


def create_binary(out: Path):
    proc=subprocess.run(['go','build','-trimpath','-ldflags=-buildid=', '-o',str(out),'.'],
                        cwd=ROOT/'native/ontos-l10-gateway',env={**os.environ,'GOTOOLCHAIN':'local','CGO_ENABLED':'0','GOPROXY':'off','GOSUMDB':'off'},
                        capture_output=True,text=True,timeout=90)
    if proc.returncode: pytest.fail('Go native compile failed: '+proc.stderr)
    assert out.exists()


@pytest.fixture(scope='module')
def gateway_binary(tmp_path_factory):
    path=tmp_path_factory.mktemp('native_gateway')/'l10-gateway'
    create_binary(path)
    return path


@pytest.fixture
def native_session(gateway_binary,tmp_path):
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    trusted=external.public_key().public_bytes_raw().hex()
    signer_seed=signer.private_bytes_raw().hex()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    sock=tmp_path/'sandbox.sock'
    keyfile=tmp_path/'signer.seed'
    keyfile.write_text(signer_seed)
    keyfile.chmod(0o600)
    p=subprocess.Popen([str(gateway_binary),'--socket',str(sock),'--tenant','tenant-a',
                        '--trusted-key',trusted,'--shell',shell.sha256,'--receipt-key-file',str(keyfile),
                        '--state-file',str(tmp_path/'checkpoint.json'),'--bootstrap'],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    for _ in range(200):
        if sock.exists():break
        if p.poll() is not None:
            pytest.fail('native gateway stopped: '+p.stderr.read())
        time.sleep(.02)
    else:pytest.fail('native socket startup timeout')
    try: yield sock,shell,external,signer.public_key()
    finally:
        p.terminate()
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)


def request(sock:Path, message:bytes):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(3)
        s.connect(str(sock))
        s.sendall(struct.pack('>I',len(message))+message)
        header=s.recv(4)
        assert len(header)==4
        size=struct.unpack('>I',header)[0]
        assert size<4096
        buff=b''
        while len(buff)<size:
            chunk=s.recv(size-len(buff))
            assert chunk
            buff+=chunk
    return json.loads(buff)


def frame(seq,chan,kind,*,cap=None,alarm=False,attestation=None):
    body={'alarm':alarm,'cap':cap,'kind':kind}
    if attestation is not None:body['attestation']=attestation
    data=json.dumps(body,separators=(',',':'),sort_keys=True).encode()
    return encode(Envelope('ontos-ipc-v1',chan,'tenant-a',f'nonce{seq}',seq,seq+1,100,data))


def strict_token(proposal,proof,key):
    public=PureIR(('add',('x',),('lit',1)))
    left=(Event('tenant-a','a','public','s1','ok',(),('tenant-a:memory',)),)
    right=(Event('tenant-a','b','public','s2','ok',('tenant-a:other',),()),)
    model=BinaryIVSCM((ResponseType(0,1,0,1,F(1)),))
    table=(model.observational(0),model.observational(1))
    return issue_release(proposal,proof,public,left,right,table,key,epoch=1,expires_tick=50)


def test_native_compiled_process_denies_unattested_dfx(native_session):
    sock,shell,external,verify=native_session
    a=request(sock,frame(0,'A','observe'))
    b=request(sock,frame(1,'B','assess'))
    c=request(sock,frame(2,'D','propose',cap='compute'))
    assert a['status']=='OBSERVED'
    assert b['status']=='ASSESSED'
    assert c['status']=='DENY_UNATTESTED'
    assert c['operational_capabilities_granted'] is False
    # Rejected message did not advance native state.
    d=request(sock,frame(2,'E','allow',cap='compute'))
    assert d['status']=='DENY_CLIENT_ALLOW'


def test_native_cross_language_signed_dfx_model_and_strict_replay(native_session):
    sock,shell,external,verify=native_session
    left=PureIR(('add',('x',),('lit',1)))
    right=PureIR(('sub',('x',),('lit',15)))
    proposal=PartitionProposal(shell.sha256,left,right,'tenant-a')
    proof=check_equivalence(left,right)
    signature=strict_token(proposal,proof,external)
    assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
    assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    receipt=request(sock,frame(2,'D','propose',cap='compute',attestation=signature))
    assert receipt['status']=='MODEL_APPROVED'
    assert receipt['cap_mask']==2
    assert receipt['request_nonce']=='nonce2'
    assert receipt['proposal_sha256']==proposal.sha256
    assert receipt['noninterference_sha256']==signature['noninterference_sha256']
    assert receipt['operational_capabilities_granted'] is False
    assert receipt['native_go_process_verified']
    rawsig=bytes.fromhex(receipt['signature_ed25519_hex'])
    signed={k:v for k,v in receipt.items() if k!='signature_ed25519_hex'}
    verify.verify(rawsig,json.dumps(signed,sort_keys=True,separators=(',',':')).encode())
    tamper=dict(receipt);tamper['cap_mask']=7
    with pytest.raises(Exception):verify.verify(rawsig,json.dumps({k:v for k,v in tamper.items() if k!='signature_ed25519_hex'},sort_keys=True,separators=(',',':')).encode())
    assert request(sock,frame(2,'D','propose',cap='compute',attestation=signature))['status']=='REPLAY_REJECTED'
    assert request(sock,frame(3,'E','allow',cap='compute'))['status']=='DENY_CLIENT_ALLOW'


def test_native_rejects_wrong_signature_version_and_corrupt_wire(native_session):
    sock,shell,external,verify=native_session
    assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
    assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    forged={'schema':'ontos-offline-dfx-approval-v1','tenant':'tenant-a','shell_sha256':shell.sha256,
            'proposal_sha256':'1'*64,'proof_sha256':'2'*64,'epoch':1,'expires_tick':30,
            'signature_ed25519_hex':'ab'*64}
    assert request(sock,frame(2,'D','propose',cap='compute',attestation=forged))['status']=='INVALID_BODY'
    corrupted=frame(2,'D','propose',cap='compute')+b' '
    assert request(sock,corrupted)['status']=='INVALID_FRAME'
    assert request(sock,frame(2,'D','propose',cap='compute'))['status']=='DENY_UNATTESTED'


def test_native_cross_tenant_and_oversize_deny(native_session):
    sock,shell,external,verify=native_session
    wrong=Envelope('ontos-ipc-v1','A','tenant-b','different',0,1,10,b'{}')
    assert request(sock,encode(wrong))['status']=='TENANT_REJECTED'
    assert request(sock,b'x'*9000)['status']=='INVALID_FRAME'


def test_native_signed_durable_recovery_never_restores_caps(gateway_binary,tmp_path):
    """Crash/restart must not reinstate the model rights or forget replay IDs."""
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    sock=tmp_path/'durable.sock'
    statefile=tmp_path/'checkpoint.json'
    keyfile=tmp_path/'signing.seed'
    keyfile.write_text(signer.private_bytes_raw().hex())
    keyfile.chmod(0o600)
    args=[str(gateway_binary),'--socket',str(sock),'--tenant','tenant-a',
          '--trusted-key',external.public_key().public_bytes_raw().hex(),
          '--shell',shell.sha256,'--receipt-key-file',str(keyfile),
          '--state-file',str(statefile)]
    def start(bootstrap=False):
        if sock.exists():sock.unlink()
        p=subprocess.Popen(args+(['--bootstrap'] if bootstrap else []),
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        for _ in range(150):
            if sock.exists():return p
            if p.poll() is not None:
                err=p.stderr.read()
                pytest.fail('native restart failed: '+err)
            time.sleep(.02)
        pytest.fail('native restart timeout')
    p=start(True)
    try:
        assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
        assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
        left=PureIR(('add',('x',),('lit',1)))
        right=PureIR(('sub',('x',),('lit',15)))
        proposal=PartitionProposal(shell.sha256,left,right,'tenant-a')
        proof=check_equivalence(left,right)
        approval=strict_token(proposal,proof,external)
        approved=request(sock,frame(2,'D','propose',cap='compute',attestation=approval))
        assert approved['status']=='MODEL_APPROVED' and approved['cap_mask']==2
        assert statefile.is_file()
    finally:
        p.terminate();p.wait(timeout=3)
    p=start(False)
    try:
        again=request(sock,frame(2,'D','propose',cap='compute',attestation=approval))
        assert again['status']=='REPLAY_REJECTED' and again['cap_mask']==2
        untrusted=request(sock,frame(3,'E','allow',cap='compute'))
        assert untrusted['status']=='DENY_CLIENT_ALLOW' and untrusted['cap_mask']==2
    finally:
        p.terminate();p.wait(timeout=3)


def test_native_tampered_checkpoint_refused_on_restart(gateway_binary,tmp_path):
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    sock=tmp_path/'tamper.sock'
    statefile=tmp_path/'checkpoint.json'
    keyfile=tmp_path/'signing.seed'
    keyfile.write_text(signer.private_bytes_raw().hex());keyfile.chmod(0o600)
    args=[str(gateway_binary),'--socket',str(sock),'--tenant','tenant-a',
          '--trusted-key',external.public_key().public_bytes_raw().hex(),
          '--shell',shell.sha256,'--receipt-key-file',str(keyfile),
          '--state-file',str(statefile)]
    p=subprocess.Popen(args+['--bootstrap'],stderr=subprocess.PIPE)
    try:
        for _ in range(150):
            if sock.exists(): break
            time.sleep(.02)
        assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
        assert statefile.exists()
    finally:
        p.terminate();p.wait(timeout=3)
    data=bytearray(statefile.read_bytes());data[len(data)//2]^=0x01;statefile.write_bytes(data)
    sock.unlink()
    result=subprocess.run(args,timeout=5,capture_output=True)
    assert result.returncode!=0
    assert not sock.exists()


def test_native_rejects_legacy_equivalence_only_signature(native_session):
    sock,shell,external,verify=native_session
    left=PureIR(('add',('x',),('lit',1)))
    right=PureIR(('sub',('x',),('lit',15)))
    proposal=PartitionProposal(shell.sha256,left,right,'tenant-a')
    proof=check_equivalence(left,right)
    legacy=make_approval(proposal,proof,external,epoch=1,expires_tick=50)
    assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
    assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    assert request(sock,frame(2,'D','propose',cap='compute',attestation=legacy))['status'] in (
        'DENY_BAD_ATTESTATION','INVALID_BODY')


def test_native_rejects_even_authentic_signature_for_excessive_harm(native_session):
    sock,shell,external,verify=native_session
    a=PureIR(('add',('x',),('lit',1)))
    b=PureIR(('sub',('x',),('lit',15)))
    proposal=PartitionProposal(shell.sha256,a,b,'tenant-a')
    proof=check_equivalence(a,b)
    token=strict_token(proposal,proof,external)
    token['harm_upper_ppm']=55000
    body={k:v for k,v in token.items() if k!='signature_ed25519_hex'}
    token['signature_ed25519_hex']=external.sign(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hex()
    assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
    assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    result=request(sock,frame(2,'D','propose',cap='compute',attestation=token))
    assert result['status']=='DENY_BAD_ATTESTATION'
    assert result['cap_mask']==7


def test_native_receipt_to_python_ae_model_no_client_self_approval(native_session):
    from omega_x_evolution.ontos_l10_approval import apply_native_dfx_receipt
    from omega_x_evolution.ontos_v63_interface import Session,Frame,run_sequence
    sock,shell,external,go_public=native_session
    old=PureIR(('add',('x',),('lit',1)))
    new=PureIR(('sub',('x',),('lit',15)))
    proposal=PartitionProposal(shell.sha256,old,new,'tenant-a')
    proof=check_equivalence(old,new)
    token=strict_token(proposal,proof,external)
    assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
    assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    receipt=request(sock,frame(2,'D','propose',cap='compute',attestation=token))
    model=Session(frozenset(('sense','compute','remember')),
                  frozenset(('sense','compute','remember')),deadline=50)
    model=run_sequence(model,(Frame('A','observe','nonce0',1),
                              Frame('B','assess','nonce1',2),
                              Frame('D','propose','nonce2',3,'compute')))
    approved=apply_native_dfx_receipt(model,receipt,go_public,proposal,token,
                                      request_nonce='nonce2',at_tick=4)
    assert approved.phase=='MODEL_APPROVED' and approved.caps==frozenset(('compute',))
    assert not approved.operational_capabilities_granted
    with pytest.raises(ValueError):apply_native_dfx_receipt(approved,receipt,go_public,proposal,token,
                                                              request_nonce='nonce2',at_tick=5)
    corrupted=dict(receipt);corrupted['cap_mask']=7
    with pytest.raises(ValueError):apply_native_dfx_receipt(model,corrupted,go_public,proposal,token,
                                                              request_nonce='nonce2',at_tick=4)
    with pytest.raises(ValueError):apply_native_dfx_receipt(model,receipt,go_public,proposal,token,
                                                              request_nonce='other',at_tick=4)


def test_native_valid_older_checkpoint_is_not_replayable(gateway_binary,tmp_path):
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    sock=tmp_path/'journal.sock'
    statefile=tmp_path/'checkpoint.json'
    keyfile=tmp_path/'signing.seed';keyfile.write_text(signer.private_bytes_raw().hex());keyfile.chmod(0o600)
    args=[str(gateway_binary),'--socket',str(sock),'--tenant','tenant-a',
          '--trusted-key',external.public_key().public_bytes_raw().hex(),
          '--shell',shell.sha256,'--receipt-key-file',str(keyfile),
          '--state-file',str(statefile)]
    proc=subprocess.Popen(args+['--bootstrap'],stderr=subprocess.PIPE)
    try:
        for _ in range(150):
            if sock.exists():break
            time.sleep(.02)
        assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
        older=statefile.read_bytes()
        assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
        assert statefile.read_bytes()!=older
    finally:proc.terminate();proc.wait(timeout=3)
    statefile.write_bytes(older)
    sock.unlink()
    result=subprocess.run(args,timeout=5,capture_output=True)
    assert result.returncode!=0
    assert not sock.exists()


def test_native_world_readable_signer_seed_denied(gateway_binary,tmp_path):
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    key=tmp_path/'world_readable.key'
    key.write_text(signer.private_bytes_raw().hex());key.chmod(0o644)
    args=[str(gateway_binary),'--socket',str(tmp_path/'socket'),'--tenant','tenant-a',
          '--trusted-key',external.public_key().public_bytes_raw().hex(),
          '--shell',shell.sha256,'--receipt-key-file',str(key),
          '--state-file',str(tmp_path/'checkpoint.json'),'--bootstrap']
    result=subprocess.run(args,capture_output=True,timeout=5)
    assert result.returncode!=0


@pytest.mark.xfail(
    strict=True,
    reason='Full rollback of both co-located signed state+anchor needs an external monotonic trust anchor',
)
def test_native_dual_file_rollback_requires_protected_external_anchor(gateway_binary, tmp_path):
    """Known physical trust-boundary limitation; intentionally not counted as PASS."""
    external=Ed25519PrivateKey.generate()
    signer=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    sock=tmp_path/'paired_rollback.sock'
    statefile=tmp_path/'checkpoint.json'
    keyfile=tmp_path/'signing.seed'
    keyfile.write_text(signer.private_bytes_raw().hex())
    keyfile.chmod(0o600)
    args=[str(gateway_binary),'--socket',str(sock),'--tenant','tenant-a',
          '--trusted-key',external.public_key().public_bytes_raw().hex(),
          '--shell',shell.sha256,'--receipt-key-file',str(keyfile),
          '--state-file',str(statefile)]
    p=subprocess.Popen(args+['--bootstrap'],stderr=subprocess.PIPE)
    try:
        for _ in range(150):
            if sock.exists():break
            time.sleep(.02)
        assert request(sock,frame(0,'A','observe'))['status']=='OBSERVED'
        old_state=statefile.read_bytes()
        old_anchor=(tmp_path/'checkpoint.json.anchor').read_bytes()
        assert request(sock,frame(1,'B','assess'))['status']=='ASSESSED'
    finally:
        p.terminate();p.wait(timeout=3)
    # An attacker who can restore both files can supply a *valid* old pair.
    statefile.write_bytes(old_state)
    (tmp_path/'checkpoint.json.anchor').write_bytes(old_anchor)
    sock.unlink()
    # Desired safety property: fail startup. Current model cannot enforce it.
    result=subprocess.run(args,timeout=2,capture_output=True)
    assert result.returncode != 0
