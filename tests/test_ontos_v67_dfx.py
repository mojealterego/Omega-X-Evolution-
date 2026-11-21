"""TDD: independent native SMT and simulated fail-closed dynamic partition update."""
from dataclasses import replace
import hashlib
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v47_pure_ir import PureIR
from omega_x_evolution.ontos_v67_dfx import (
    StaticShell, PartitionProposal, DFXState, check_equivalence,
    make_approval, verify_approval, transition, verify_invariants,
)

ROOT = 'e0'*32

def ref(): return PureIR(('add',('x',),('lit',1)))
def optimized(): return PureIR(('sub',('x',),('lit',15)))
def wrong(): return PureIR(('xor',('x',),('lit',1)))

def fixtures():
    secret=Ed25519PrivateKey.generate()
    shell=StaticShell('shell-v1', ROOT, 'tenant-a',4)
    guard=DFXState(shell=shell, anchor_sha256=shell.sha256, trust_public_sha256=hashlib.sha256(secret.public_key().public_bytes_raw()).hexdigest(), active_sha256=hashlib.sha256(b'golden').hexdigest(),
                   golden_sha256=hashlib.sha256(b'golden').hexdigest(),deadline_tick=100)
    candidate=PartitionProposal(shell.sha256,ref(),optimized(),'tenant-a')
    return shell, guard, candidate, secret


def test_exact_native_z3_qfbv_equivalence_and_witnesses():
    good=check_equivalence(ref(),optimized())
    assert good['status']=='PASS_EXHAUSTIVE_AND_Z3' and good['z3']=='unsat'
    assert good['checked_cases']==256 and good['counterexample'] is None
    bad=check_equivalence(ref(),wrong())
    assert bad['status']=='FAIL_COUNTEREXAMPLE' and bad['z3']=='sat'
    assert bad['counterexample'] is not None


def test_bound_127_never_proves():
    r=check_equivalence(ref(),optimized(),limit=127)
    assert r['status']=='UNKNOWN_BOUND' and r['checked_cases']==127


def test_signed_approval_binds_shell_semantics_tenant_candidate_and_epoch():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    receipt=make_approval(candidate,proof,secret,epoch=1,expires_tick=20)
    assert verify_approval(candidate,proof,receipt,secret.public_key(),at_tick=10,epoch=1)
    assert not verify_approval(candidate,proof,receipt,Ed25519PrivateKey.generate().public_key(),at_tick=10,epoch=1)
    assert not verify_approval(candidate,proof,receipt,secret.public_key(),at_tick=21,epoch=1)
    assert not verify_approval(candidate,proof,receipt,secret.public_key(),at_tick=10,epoch=2)
    other=PartitionProposal('f'*64,ref(),optimized(),'tenant-a')
    assert not verify_approval(other,proof,receipt,secret.public_key(),at_tick=10,epoch=1)


def strict_approval(candidate,proof,key,*,expires_tick=40):
    from omega_x_evolution.ontos_l10_release import issue_release
    from omega_x_evolution.ontos_v55_scm import ResponseType, BinaryIVSCM
    from omega_x_evolution.ontos_v65_hypertraces import Event
    from fractions import Fraction as F
    safe=PureIR(('add',('x',),('lit',1)))
    a=(Event('tenant-a','a','public','s1','ok',(),('tenant-a:memory',)),)
    b=(Event('tenant-a','b','public','s2','ok',('tenant-a:other',),()),)
    m=BinaryIVSCM((ResponseType(0,1,0,1,F(1)),))
    return issue_release(candidate,proof,safe,a,b,
                         (m.observational(0),m.observational(1)),key,epoch=1,expires_tick=expires_tick)


def test_dfx_nominal_and_reset_preserves_static_shell():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    approval=strict_approval(candidate,proof,secret,expires_tick=30)
    p=transition(guard, 'prepare', at_tick=9, proposal=candidate,
                 proof=proof,approval=approval,public_key=secret.public_key())
    assert p.pending_sha256==candidate.sha256 and p.shell==shell
    c=transition(p,'commit',at_tick=10,proposal=candidate,
                 proof=proof,approval=approval,public_key=secret.public_key())
    assert c.active_sha256==candidate.sha256 and not c.pending_sha256
    assert c.shell.sha256==shell.sha256
    assert c.operational_bitstream_programmed is False
    assert verify_invariants((guard,p,c))
    reset=transition(c,'reset',at_tick=11)
    assert reset.active_sha256==guard.golden_sha256
    assert reset.shell==shell and reset.epoch==2


def test_attacker_cannot_self_approve_or_change_static_shell():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    forged=strict_approval(candidate,proof,Ed25519PrivateKey.generate(),expires_tick=30)
    with pytest.raises(ValueError): transition(guard,'prepare',at_tick=9,proposal=candidate,proof=proof,
                                                approval=forged,public_key=secret.public_key())
    bad=PartitionProposal(shell.sha256,ref(),wrong(),'tenant-a')
    badproof=check_equivalence(ref(),wrong())
    with pytest.raises(ValueError): strict_approval(bad,badproof,secret,expires_tick=30)
    with pytest.raises(ValueError): replace(guard,shell=replace(shell,source_sha256='bad'))


def test_timeout_invalidates_token_and_no_partial_commit():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    approval=strict_approval(candidate,proof,secret,expires_tick=12)
    pending=transition(guard,'prepare',at_tick=10,proposal=candidate,proof=proof,
                       approval=approval,public_key=secret.public_key())
    timeout=transition(pending,'timeout',at_tick=13)
    assert timeout.active_sha256==guard.active_sha256 and timeout.pending_sha256 is None
    with pytest.raises(ValueError): transition(timeout,'commit',at_tick=14,proposal=candidate,
                                                proof=proof,approval=approval,public_key=secret.public_key())


def test_replay_approval_rejected_on_next_epoch():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    token=strict_approval(candidate,proof,secret,expires_tick=30)
    ready=transition(guard,'prepare',at_tick=9,proposal=candidate,proof=proof,approval=token,public_key=secret.public_key())
    done=transition(ready,'commit',at_tick=10,proposal=candidate,proof=proof,approval=token,public_key=secret.public_key())
    with pytest.raises(ValueError): transition(done,'prepare',at_tick=11,proposal=candidate,proof=proof,approval=token,public_key=secret.public_key())


def test_state_tamper_detected_even_for_frozen_dataclass():
    shell,guard,candidate,secret=fixtures()
    object.__setattr__(guard,'active_sha256','0'*64)
    with pytest.raises(ValueError):guard.__post_init__()


def test_v67_valid_but_modified_static_shell_digest_rejected():
    shell,guard,candidate,secret=fixtures()
    mutated=replace(shell,source_sha256='f'*64)
    with pytest.raises(ValueError,match='anchor'):
        replace(guard,shell=mutated)


def test_v67_approved_receipt_not_usable_for_other_tenant():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    receipt=strict_approval(candidate,proof,secret,expires_tick=20)
    other=PartitionProposal(candidate.shell_sha256,ref(),optimized(),'tenant-b')
    assert not verify_approval(other,proof,receipt,secret.public_key(),at_tick=10,epoch=1)


def test_v67_strict_dfx_transition_refuses_weak_equivalence_only_approval():
    shell,guard,candidate,secret=fixtures()
    proof=check_equivalence(ref(),optimized())
    legacy=make_approval(candidate,proof,secret,epoch=1,expires_tick=30)
    with pytest.raises(ValueError,match='release'):
        transition(guard,'prepare',at_tick=10,proposal=candidate,
                   proof=proof,approval=legacy,public_key=secret.public_key())
