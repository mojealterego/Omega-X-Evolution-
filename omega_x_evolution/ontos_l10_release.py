"""Offline L10 issuance: externally signed, four-obligation pre-commit evidence.

The issuer *recomputes* independent solver/LP/trace results; candidates cannot
self-assert a PASS. This is not a production key hierarchy or operational TCB.
No verification receipt can configure hardware or add an OS capability.
"""
from __future__ import annotations
import hashlib
import json
import math
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey,Ed25519PublicKey
from .ontos_v47_pure_ir import PureIR
from .ontos_v55_scm import BinaryIVSCM
from .ontos_v56_bounds import iv_bounds
from .ontos_v65_hypertraces import Event, check_interleavings,check_pairwise
from .ontos_l10_formal import check_symbolic_noninterference
from .ontos_v67_dfx import PartitionProposal,check_equivalence

_SCHEMA='ontos-l10-release-v2'
_POLICY='ontos-l10-policy-4-verifiers-v1'

def _json(data):
    return json.dumps(data,sort_keys=True,separators=(',',':'),allow_nan=False,
                      ensure_ascii=True).encode('ascii')

def _sha(data):return hashlib.sha256(_json(data)).hexdigest()

def _evidence(p,proof,program,left,right,iv_table):
    if (type(p) is not PartitionProposal or type(proof) is not dict
        or type(program) is not PureIR or type(left) is not tuple or type(right) is not tuple):
        raise ValueError('typed release evidence required')
    # Verification independently runs the entire 256-value reference oracle
    # plus an actual separate libz3 process; digest alone never passes.
    if check_equivalence(p.reference,p.replacement) != proof or proof.get('status')!='PASS_EXHAUSTIVE_AND_Z3':
        raise ValueError('ir equivalence not verified')
    flow=check_symbolic_noninterference(program)
    if flow['status']!='PASS_QFBV_UNSAT':
        raise ValueError('noninterference not proved on finite domain')
    traces=check_pairwise((left,right),max_pairs=64)
    if traces['status']!='PASS_FINITE':
        raise ValueError('low trace noninterference not demonstrated')
    schedules=check_interleavings(left,right,max_schedules=10000)
    if schedules['status']!='PASS_FINITE' or schedules['conflicts']:
        raise ValueError('read-write conflict found or budget unknown')
    risk=iv_bounds(iv_table,target='harm')
    if risk['status']!='PASS' or type(risk['upper']) is not float or not math.isfinite(risk['upper']):
        raise ValueError('harm bound unknown')
    # Numercially solved interval must be comfortably inside policy guard;
    # marginal floating-point values are conservatively rejected.
    if risk['upper']>.05-1e-9 or risk['lower']<0:
        raise ValueError('harm upper bound violates policy')
    return {'equivalence_sha256':_sha(proof),
            'noninterference_sha256':_sha([flow,traces]),
            'schedules_sha256':_sha(schedules),
            'harm_bound_sha256':_sha(risk),
            'harm_upper_ppm':int(math.ceil(max(0.,risk['upper'])*1_000_000)),
            'policy_version':_POLICY}


def _fields(p,proof,program,left,right,iv_table,epoch,expires_tick):
    if type(epoch) is not int or not 1<=epoch<=1000 or type(expires_tick) is not int or not 0<=expires_tick<2**63:
        raise ValueError('release epoch/expiry')
    p.__post_init__()
    return {'schema':_SCHEMA, 'shell_sha256':p.shell_sha256,
            'tenant':p.tenant, 'proposal_sha256':p.sha256,
            'epoch':epoch,'expires_tick':expires_tick,
            **_evidence(p,proof,program,left,right,iv_table)}


def issue_release(proposal: PartitionProposal,proof:dict,public_program:PureIR,
                  trace_left:tuple[Event,...],trace_right:tuple[Event,...],iv_table:tuple,
                  trusted_signer:Ed25519PrivateKey,*,epoch:int,expires_tick:int)->dict:
    if not isinstance(trusted_signer,Ed25519PrivateKey):
        raise ValueError('out-of-loop signing key required')
    body=_fields(proposal,proof,public_program,trace_left,trace_right,iv_table,epoch,expires_tick)
    return {**body,'signature_ed25519_hex':trusted_signer.sign(_json(body)).hex()}


def verify_release(token:dict,proposal:PartitionProposal,proof:dict,public_program:PureIR,
                   trace_left:tuple[Event,...],trace_right:tuple[Event,...],iv_table:tuple,
                   trusted_public_key:Ed25519PublicKey,*,at_tick:int,epoch:int)->bool:
    try:
        if (type(token) is not dict or not isinstance(trusted_public_key,Ed25519PublicKey)
            or type(at_tick) is not int or not 0<=at_tick<2**63
            or type(epoch) is not int or not 1<=epoch<=1000
            or type(token.get('expires_tick')) is not int or at_tick>token['expires_tick']):
            return False
        expected=_fields(proposal,proof,public_program,trace_left,trace_right,iv_table,
                         epoch,token['expires_tick'])
        if set(token)!=set(expected)|{'signature_ed25519_hex'} or any(token.get(k)!=v for k,v in expected.items()):
            return False
        sig=bytes.fromhex(token['signature_ed25519_hex'])
        trusted_public_key.verify(sig,_json(expected))
        return True
    except (ValueError,TypeError,KeyError,InvalidSignature,ArithmeticError):
        return False
