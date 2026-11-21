"""Bind a native gateway's signed DFX verdict to the finite A-E state machine.

The gateway never grants a real OS permission; this only allows the next
Python FSM label after independently validating an Ed25519 receipt. No trust
is placed in self-reported E:allow frames from the candidate.
"""
from __future__ import annotations
import json
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from .ontos_v63_interface import Session,Frame,transition
from .ontos_v67_dfx import PartitionProposal

_KEYS=frozenset({
    'status','phase','sequence','cap_mask','operational_capabilities_granted',
    'native_go_process_verified','rust_zenoh_wasi_verified','physical_fpga_reconfigured',
    'tenant','shell_sha256','request_nonce','request_sequence','proposal_sha256',
    'equivalence_sha256','noninterference_sha256','schedules_sha256',
    'harm_bound_sha256','harm_upper_ppm','policy_version','epoch','signature_ed25519_hex'})


def _canonical(v: dict) -> bytes:
    return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=True,
                      allow_nan=False).encode('ascii')


def apply_native_dfx_receipt(state:Session,receipt:dict,public_key:Ed25519PublicKey,
                             proposal:PartitionProposal,release:dict,*,
                             request_nonce:str,at_tick:int)->Session:
    if (type(state) is not Session or type(receipt) is not dict or
            type(proposal) is not PartitionProposal or type(release) is not dict or
            not isinstance(public_key,Ed25519PublicKey) or type(request_nonce) is not str or
            type(at_tick) is not int or not 0<=at_tick<2**63):
        raise ValueError('signed gateway receipt contract')
    state.__post_init__();proposal.__post_init__()
    if set(receipt)!=_KEYS or not request_nonce in state.seen_nonces:
        raise ValueError('receipt fields or nonce unbound')
    expected={
        'status':'MODEL_APPROVED','phase':'MODEL_APPROVED','tenant':proposal.tenant,
        'shell_sha256':proposal.shell_sha256,'proposal_sha256':proposal.sha256,
        'request_nonce':request_nonce,'request_sequence':state.seen_nonces.index(request_nonce),
        'cap_mask':2,'operational_capabilities_granted':False,
        'native_go_process_verified':True,'rust_zenoh_wasi_verified':False,
        'physical_fpga_reconfigured':False,
        'equivalence_sha256':release.get('equivalence_sha256'),
        'noninterference_sha256':release.get('noninterference_sha256'),
        'schedules_sha256':release.get('schedules_sha256'),
        'harm_bound_sha256':release.get('harm_bound_sha256'),
        'harm_upper_ppm':release.get('harm_upper_ppm'),
        'policy_version':'ontos-l10-policy-4-verifiers-v1','epoch':release.get('epoch'),
    }
    if (state.phase!='PROPOSED_D' or state.pending_cap!='compute' or
            release.get('schema')!='ontos-l10-release-v2' or
            release.get('proposal_sha256')!=proposal.sha256 or
            receipt.get('sequence')!=len(state.seen_nonces) or
            type(receipt.get('harm_upper_ppm')) is not int or
            not 0<=receipt['harm_upper_ppm']<=50000 or
            any(receipt.get(k)!=v for k,v in expected.items())):
        raise ValueError('gateway receipt not bound to DFX model')
    try:
        signature=bytes.fromhex(receipt['signature_ed25519_hex'])
        if len(signature)!=64:raise ValueError('signature size')
        signed={k:v for k,v in receipt.items() if k!='signature_ed25519_hex'}
        public_key.verify(signature,_canonical(signed))
    except (InvalidSignature,ValueError,TypeError,KeyError) as exc:
        raise ValueError('gateway receipt signature rejected') from exc
    # This is ONLY the finite model's label. The authorized gateway cannot
    # directly call host actions or modify kernel permission maps.
    return transition(state,Frame('E','allow','gateway_'+request_nonce,
                                  at_tick,'compute',False))
