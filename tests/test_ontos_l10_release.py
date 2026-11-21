"""Red/green: release token binds independently checked causal, SMT and trace evidence."""
from fractions import Fraction as F
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_v55_scm import ResponseType, BinaryIVSCM
from omega_x_evolution.ontos_v65_hypertraces import Event
from omega_x_evolution.ontos_v67_dfx import StaticShell,PartitionProposal,check_equivalence
from omega_x_evolution.ontos_l10_release import issue_release, verify_release


def evidence():
    shell=StaticShell('shell-v1','e0'*32,'tenant-a',4)
    old=PureIR(('add',('x',),('lit',1)))
    new=PureIR(('sub',('x',),('lit',15)))
    p=PartitionProposal(shell.sha256,old,new,'tenant-a')
    proof=check_equivalence(old,new)
    safe=PureIR(('add',('x',),('lit',1)))
    a=(Event('tenant-a','a','public','s1','ok',(),('tenant-a:memory',)),)
    b=(Event('tenant-a','b','public','s2','ok',('tenant-a:other',),()),)
    model=BinaryIVSCM((ResponseType(0,1,0,1,F(1)),))
    table=(model.observational(0),model.observational(1))
    return p,proof,safe,a,b,table


def test_issued_token_requires_independently_checked_all_four_obligations():
    signer=Ed25519PrivateKey.generate()
    p,proof,safe,a,b,table=evidence()
    token=issue_release(p,proof,safe,a,b,table,signer,epoch=1,expires_tick=100)
    assert token['schema']=='ontos-l10-release-v2'
    assert token['harm_upper_ppm']==0
    assert token['proposal_sha256']==p.sha256
    assert len(token['noninterference_sha256'])==64
    assert len(token['schedules_sha256'])==64
    assert verify_release(token,p,proof,safe,a,b,table,signer.public_key(),at_tick=10,epoch=1)
    assert not verify_release(token,p,proof,safe,a,b,table,signer.public_key(),at_tick=101,epoch=1)


def test_harm_unidentified_is_not_equivalent_to_zero():
    p,proof,safe,a,b,table=evidence()
    unknown=BinaryIVSCM((ResponseType(0,0,1,1,F(1)),))
    with pytest.raises(ValueError,match='harm'):
        issue_release(p,proof,safe,a,b,(unknown.observational(0),unknown.observational(1)),
                      Ed25519PrivateKey.generate(),epoch=1,expires_tick=100)


def test_conflict_and_information_flow_block_release():
    p,proof,safe,a,b,table=evidence()
    bad=(Event('tenant-a','b','public','s2','ok',('tenant-a:memory',),()),)
    with pytest.raises(ValueError,match='conflict'):
        issue_release(p,proof,safe,a,bad,table,Ed25519PrivateKey.generate(),epoch=1,expires_tick=100)
    leaking=PureIR(('xor',('x',),('y',)))
    with pytest.raises(ValueError,match='noninterference'):
        issue_release(p,proof,leaking,a,b,table,Ed25519PrivateKey.generate(),epoch=1,expires_tick=100)


def test_tamper_wrong_issuer_and_candidate_epoch_fail_closed():
    signer=Ed25519PrivateKey.generate()
    p,proof,safe,a,b,table=evidence()
    tok=issue_release(p,proof,safe,a,b,table,signer,epoch=1,expires_tick=40)
    assert not verify_release({**tok,'harm_upper_ppm':50000},p,proof,safe,a,b,table,
                              signer.public_key(),at_tick=10,epoch=1)
    assert not verify_release(tok,p,proof,safe,a,b,table,Ed25519PrivateKey.generate().public_key(),
                              at_tick=10,epoch=1)
    assert not verify_release(tok,p,proof,safe,a,b,table,signer.public_key(),at_tick=10,epoch=2)
    assert not verify_release(tok,p,proof,safe,a,b,table,signer.public_key(),at_tick=41,epoch=1)


def test_old_weak_equivalence_only_approval_not_accepted():
    from omega_x_evolution.ontos_v67_dfx import make_approval
    p,proof,safe,a,b,table=evidence()
    key=Ed25519PrivateKey.generate()
    old=make_approval(p,proof,key,epoch=1,expires_tick=40)
    assert not verify_release(old,p,proof,safe,a,b,table,key.public_key(),at_tick=10,epoch=1)
