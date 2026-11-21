"""Bounded DFX finite digital twin with a native Z3 QF_BV worker and signed receipts.

Only pure i4 combinational IR is eligible. The kernel verifies exact 256-case
semantics, then separately asks system libz3 to refute inequivalence. A signed
receipt is bound to the immutable static shell, both trees, tenant, epoch and
expiry. No FPGA, ICAP, HDL parser or operational token is accessed.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
import ctypes
import ctypes.util
import hashlib
import json
import re
import subprocess
import sys

from .ontos_v47_pure_ir import PureIR, evaluate
from .ontos_v64_certificate import certify, verify_certificate

_HEX = re.compile(r'[0-9a-f]{64}\Z')
_NAME = re.compile(r'[a-z0-9-]{1,64}\Z')
_OPERATIONS = {'add':'bvadd','sub':'bvsub','mul':'bvmul','xor':'bvxor','and':'bvand','or':'bvor'}


def _canonical(data: object) -> bytes:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',',':'), allow_nan=False).encode('ascii')


def _hash(data: object) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def _smt_tree(t: tuple) -> str:
    op=t[0]
    if op in ('x','y'): return op
    if op == 'lit': return '(_ bv'+str(t[1])+' 4)'
    return '('+_OPERATIONS[op]+' '+_smt_tree(t[1])+' '+_smt_tree(t[2])+')'


def _solver_command(left: PureIR, right: PureIR) -> str:
    return ('(set-logic QF_BV)\n(set-option :timeout 3000)\n'
            '(declare-const x (_ BitVec 4))\n(declare-const y (_ BitVec 4))\n'
            '(assert (distinct '+_smt_tree(left.tree)+' '+_smt_tree(right.tree)+'))\n(check-sat)\n')


def _native_z3_worker(smt: str) -> str:
    """Executed only in a bounded child process; SMT input is generated from IR."""
    if type(smt) is not str or len(smt)>65536:
        raise ValueError('SMT size')
    libname=ctypes.util.find_library('z3')
    if libname is None: return 'unavailable'
    z=ctypes.CDLL(libname)
    p=ctypes.c_void_p
    for name, args, ret in [
        ('Z3_mk_config',[],p),('Z3_mk_context',[p],p),
        ('Z3_del_config',[p],None),('Z3_del_context',[p],None),
        ('Z3_eval_smtlib2_string',[p,ctypes.c_char_p],ctypes.c_char_p)
    ]:
        fn=getattr(z,name);fn.argtypes=args;fn.restype=ret
    cfg=z.Z3_mk_config()
    if not cfg: return 'error'
    context=z.Z3_mk_context(cfg)
    z.Z3_del_config(cfg)
    if not context: return 'error'
    try:
        raw=z.Z3_eval_smtlib2_string(context,smt.encode('ascii'))
        if raw is None: return 'error'
        answer=raw.decode('ascii').strip()
        return answer if answer in ('sat','unsat','unknown') else 'error'
    finally:
        z.Z3_del_context(context)


def _run_z3(left: PureIR, right: PureIR, *, timeout_s: int=5) -> str:
    if type(timeout_s) is not int or not 1<=timeout_s<=10:
        raise ValueError('SMT timeout')
    try:
        result=subprocess.run(
            [sys.executable,'-m','omega_x_evolution.ontos_v67_dfx','--worker'],
            input=_solver_command(left,right),text=True, capture_output=True,
            timeout=timeout_s, check=False)
    except (OSError,subprocess.TimeoutExpired):
        return 'unavailable'
    if result.returncode or result.stderr.strip() or result.stdout.strip() not in ('sat','unsat','unknown'):
        return 'error'
    return result.stdout.strip()


def check_equivalence(left: PureIR, right: PureIR, *, limit: int=256) -> dict:
    if type(left) is not PureIR or type(right) is not PureIR or type(limit) is not int or not 1<=limit<=256:
        raise ValueError('i4 programs and finite limit')
    left.__post_init__();right.__post_init__()
    proof=certify(left,right,max_cases=limit)
    # A limited proof is UNKNOWN regardless of solver outcomes; do not use it
    # to silently bypass the all-input reference witness.
    if proof['status']=='UNKNOWN_BOUND':
        return {'status':'UNKNOWN_BOUND','z3':'not-run','checked_cases':limit,
                'counterexample':None,'ir_proof_sha256':proof['certificate_sha256']}
    z3_status=_run_z3(left,right)
    if proof['status']=='FAIL_COUNTEREXAMPLE':
        return {'status':'FAIL_COUNTEREXAMPLE' if z3_status=='sat' else 'UNKNOWN_SOLVER',
                'z3':z3_status, 'checked_cases':proof['cases'],
                'counterexample':proof['counterexample'],
                'ir_proof_sha256':proof['certificate_sha256']}
    if not verify_certificate(left,right,proof):
        raise ArithmeticError('independent i4 certificate verifier rejected proof')
    return {'status':'PASS_EXHAUSTIVE_AND_Z3' if z3_status=='unsat' else 'UNKNOWN_SOLVER',
            'z3':z3_status,'checked_cases':256,'counterexample':None,
            'ir_proof_sha256':proof['certificate_sha256']}


@dataclass(frozen=True, slots=True)
class StaticShell:
    schema: str
    source_sha256: str
    tenant: str
    width: int

    def __post_init__(self):
        if (self.schema!='shell-v1' or type(self.source_sha256) is not str
                or _HEX.fullmatch(self.source_sha256) is None
                or type(self.tenant) is not str or _NAME.fullmatch(self.tenant) is None
                or type(self.width) is not int or self.width!=4):
            raise ValueError('immutable static shell manifest')

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return _hash(['ontos-static-shell-v1',self.schema,self.source_sha256,self.tenant,self.width])


@dataclass(frozen=True, slots=True)
class PartitionProposal:
    shell_sha256: str
    reference: PureIR
    replacement: PureIR
    tenant: str

    def __post_init__(self):
        if (type(self.shell_sha256) is not str or _HEX.fullmatch(self.shell_sha256) is None
                or type(self.reference) is not PureIR or type(self.replacement) is not PureIR
                or type(self.tenant) is not str or _NAME.fullmatch(self.tenant) is None):
            raise ValueError('finite DFX proposal contract')
        self.reference.__post_init__();self.replacement.__post_init__()

    @property
    def sha256(self) -> str:
        self.__post_init__()
        return _hash(['ontos-dfx-proposal-v1',self.shell_sha256,self.tenant,
                      self.reference.tree,self.replacement.tree])


def _approval_fields(proposal: PartitionProposal, proof: dict, epoch: int, expires_tick: int) -> dict:
    return {'schema':'ontos-offline-dfx-approval-v1','shell_sha256':proposal.shell_sha256,
            'tenant':proposal.tenant,'proposal_sha256':proposal.sha256,
            'proof_sha256':_hash(proof),'epoch':epoch,'expires_tick':expires_tick}


def make_approval(proposal: PartitionProposal, proof: dict,
                  signing_key: Ed25519PrivateKey, *, epoch: int, expires_tick: int) -> dict:
    if (type(proposal) is not PartitionProposal or type(proof) is not dict
            or not isinstance(signing_key,Ed25519PrivateKey)
            or type(epoch) is not int or not 1<=epoch<=1000
            or type(expires_tick) is not int or not 0<=expires_tick<2**63):
        raise ValueError('trusted signer and bounded receipt required')
    if check_equivalence(proposal.reference,proposal.replacement)!=proof or proof.get('status')!='PASS_EXHAUSTIVE_AND_Z3':
        raise ValueError('unproven candidate cannot be signed')
    payload=_approval_fields(proposal,proof,epoch,expires_tick)
    signature=signing_key.sign(_canonical(payload))
    return {**payload,'signature_ed25519_hex':signature.hex()}


def verify_approval(proposal: PartitionProposal, proof: dict, approval: dict,
                    public_key: Ed25519PublicKey, *, at_tick: int, epoch: int) -> bool:
    try:
        if (type(approval) is not dict or not isinstance(public_key,Ed25519PublicKey)
                or type(at_tick) is not int or not 0<=at_tick<2**63
                or type(epoch) is not int or not 1<=epoch<=1000
                or type(proposal) is not PartitionProposal or type(proof) is not dict
                or check_equivalence(proposal.reference,proposal.replacement) != proof
                or proof.get('status')!='PASS_EXHAUSTIVE_AND_Z3'):
            return False
        canonical=_approval_fields(proposal,proof,epoch,approval.get('expires_tick'))
        if (type(approval.get('expires_tick')) is not int or
                at_tick>approval['expires_tick'] or set(approval)!=set(canonical)|{'signature_ed25519_hex'}):
            return False
        signature=bytes.fromhex(approval['signature_ed25519_hex'])
        if len(signature)!=64: return False
        public_key.verify(signature,_canonical(canonical))
        return all(approval[k]==v for k,v in canonical.items())
    except (ValueError,TypeError,KeyError,InvalidSignature,RecursionError):
        return False


@dataclass(frozen=True, slots=True)
class DFXState:
    shell: StaticShell
    anchor_sha256: str
    trust_public_sha256: str
    active_sha256: str
    golden_sha256: str
    deadline_tick: int
    phase: str = 'IDLE'
    epoch: int = 1
    last_tick: int = 0
    pending_sha256: str | None = None
    committed: tuple[str,...] = ()
    audit: tuple[str,...] = ()

    def __post_init__(self):
        if (type(self.shell) is not StaticShell or type(self.anchor_sha256) is not str
                or _HEX.fullmatch(self.anchor_sha256) is None
                or self.shell.sha256 != self.anchor_sha256
                or type(self.trust_public_sha256) is not str
                or _HEX.fullmatch(self.trust_public_sha256) is None
                or type(self.active_sha256) is not str
                or type(self.golden_sha256) is not str
                or _HEX.fullmatch(self.active_sha256) is None
                or _HEX.fullmatch(self.golden_sha256) is None
                or type(self.deadline_tick) is not int or not 0<=self.deadline_tick<2**63
                or type(self.last_tick) is not int or not 0<=self.last_tick<2**63
                or type(self.epoch) is not int or not 1<=self.epoch<=1000
                or self.phase not in ('IDLE','PREPARED','ACTIVE','LOCKDOWN')
                or type(self.committed) is not tuple or len(self.committed)>1000
                or any(type(k) is not str or _HEX.fullmatch(k) is None for k in self.committed)
                or type(self.audit) is not tuple or len(self.audit)>1024
                or any(type(x) is not str or len(x)>128 for x in self.audit)
                or self.active_sha256 not in (self.golden_sha256, *self.committed)
                or (self.phase=='PREPARED') != (self.pending_sha256 is not None)
                or self.pending_sha256 is not None and (type(self.pending_sha256) is not str or _HEX.fullmatch(self.pending_sha256) is None)
                or self.phase=='LOCKDOWN' and self.pending_sha256 is not None):
            raise ValueError('DFX static-shell anchor/state contract')
        self.shell.__post_init__()

    @property
    def operational_bitstream_programmed(self) -> bool:
        return False


def verify_strict_release(proposal:PartitionProposal,proof:dict,token:dict,
                          signer_public:Ed25519PublicKey,*,at_tick:int,epoch:int,
                          pinned_pub_sha256:str)->bool:
    """The only promotion path: separately issued four-obligation signed claim.

    Native Z3/LP verification is performed by the *issuer* in l10_release;
    the DFX guard cryptographically verifies it against its pinned trust key.
    """
    try:
        if (type(proposal) is not PartitionProposal or type(proof) is not dict
                or type(token) is not dict or not isinstance(signer_public,Ed25519PublicKey)
                or type(at_tick) is not int or not 0<=at_tick<2**63
                or type(epoch) is not int or not 1<=epoch<=1000
                or hashlib.sha256(signer_public.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw)).hexdigest()!=pinned_pub_sha256):
            return False
        required={'schema','shell_sha256','tenant','proposal_sha256','equivalence_sha256',
                  'noninterference_sha256','schedules_sha256','harm_bound_sha256',
                  'harm_upper_ppm','policy_version','epoch','expires_tick',
                  'signature_ed25519_hex'}
        if (set(token)!=required or token['schema']!='ontos-l10-release-v2'
                or token['policy_version']!='ontos-l10-policy-4-verifiers-v1'
                or token['shell_sha256']!=proposal.shell_sha256
                or token['tenant']!=proposal.tenant
                or token['proposal_sha256']!=proposal.sha256
                or token['equivalence_sha256']!=_hash(proof)
                or any(type(token[k]) is not str or _HEX.fullmatch(token[k]) is None
                       for k in ('noninterference_sha256','schedules_sha256','harm_bound_sha256'))
                or type(token['harm_upper_ppm']) is not int or not 0<=token['harm_upper_ppm']<=50000
                or type(token['epoch']) is not int or token['epoch']!=epoch
                or type(token['expires_tick']) is not int or not 0<=at_tick<=token['expires_tick']):
            return False
        fields={k:v for k,v in token.items() if k!='signature_ed25519_hex'}
        signature=bytes.fromhex(token['signature_ed25519_hex'])
        if len(signature)!=64:return False
        signer_public.verify(signature,_canonical(fields))
        return True
    except (ValueError,TypeError,KeyError,InvalidSignature):
        return False


def transition(state: DFXState, action: str, *, at_tick: int,
               proposal: PartitionProposal | None=None, proof: dict | None=None,
               approval: dict | None=None, public_key: Ed25519PublicKey | None=None) -> DFXState:
    if (type(state) is not DFXState or type(action) is not str or
            action not in ('prepare','commit','timeout','reset')
            or type(at_tick) is not int or not 0<=at_tick<2**63):
        raise ValueError('bounded DFX transition')
    state.__post_init__()
    if at_tick<state.last_tick: raise ValueError('clock regression')
    log=state.audit+(f'{action}:{at_tick}:{state.epoch}',)
    if len(log)>1024:raise ValueError('audit budget')
    if action=='timeout' or at_tick>state.deadline_tick:
        return replace(state,phase='LOCKDOWN',pending_sha256=None,last_tick=at_tick,audit=log)
    if action=='reset':
        if state.epoch==1000:raise ValueError('epoch exhausted')
        return replace(state,phase='IDLE',pending_sha256=None,active_sha256=state.golden_sha256,
                       epoch=state.epoch+1,last_tick=at_tick,audit=log)
    if (type(proposal) is not PartitionProposal or proposal.shell_sha256!=state.shell.sha256
            or proposal.tenant!=state.shell.tenant
            or type(proof) is not dict or type(approval) is not dict
            or not verify_strict_release(proposal,proof,approval,public_key,
                                         at_tick=at_tick,epoch=state.epoch,
                                         pinned_pub_sha256=state.trust_public_sha256)):
        raise ValueError('DFX v2 release authorization rejected')
    if action=='prepare' and state.phase=='IDLE':
        return replace(state,phase='PREPARED',pending_sha256=proposal.sha256,
                       last_tick=at_tick,audit=log)
    if action=='commit' and state.phase=='PREPARED' and state.pending_sha256==proposal.sha256:
        return replace(state,phase='ACTIVE',active_sha256=proposal.sha256,pending_sha256=None,
                       committed=state.committed+(proposal.sha256,),last_tick=at_tick,audit=log)
    raise ValueError('invalid DFX state transition')


def verify_invariants(states: tuple[DFXState, ...]) -> bool:
    if type(states) is not tuple or not states:return False
    try:
        shell=states[0].shell
        for state in states:
            state.__post_init__()
            if state.shell!=shell or state.anchor_sha256 != states[0].anchor_sha256 or state.trust_public_sha256 != states[0].trust_public_sha256 or state.operational_bitstream_programmed:return False
        return all(b.last_tick>=a.last_tick and b.epoch>=a.epoch
                   for a,b in zip(states,states[1:]))
    except ValueError:
        return False


def _worker_entry() -> int:
    raw=sys.stdin.read(65537)
    if len(raw)>65536:return 2
    print(_native_z3_worker(raw))
    return 0


if __name__=='__main__':
    if sys.argv[1:]!=['--worker']:
        sys.exit(2)
    sys.exit(_worker_entry())
