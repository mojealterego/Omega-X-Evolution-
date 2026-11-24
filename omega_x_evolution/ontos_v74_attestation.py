"""Authenticate a complete reference campaign and append it to a pinned plan.

Verification recomputes the report and run evidence digests. It is not proof
of independent execution or a grant of L12 acceptance. Test-only reference
results cannot be converted into production evidence by signing them.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_receipts import ReceiptScope, sign_receipt, verify_receipt
from .ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from .ontos_v72_checkpoint_note import Checkpoint, sign_note
from .ontos_v72_checkpoint_chain import CheckpointChain
from .ontos_v74_campaign import CampaignPlan, Run, analyze_campaign

_HEX = re.compile(r'[0-9a-f]{64}\Z',re.ASCII)


def _digest(obj):
    return sha256(canonical_json(obj)).hexdigest()


def _context(plan, pin, scope):
    if (type(plan) is not CampaignPlan or type(pin) is not str or plan.digest()!=pin
            or type(scope) is not ReceiptScope or scope.level_id!='L12' or scope.gate_id!='GATE-04'):
        raise ValueError('pinned reference plan and L12 GATE-04 evidence scope required')
    return canonical_json({'kind':'v74-preregistration','plan_sha256':pin,'scope':scope.body()})


def _material(raw,plan,pin,scope):
    anchor = _context(plan,pin,scope)
    obj = parse_json(raw)
    if (type(obj) is not dict or set(obj)!={'schema','verification_mode','test_keys_only',
            'plan_sha256','report','records','details','release_authorized'}
            or obj['schema']!='omega-v74-reference-execution-v1' or obj['verification_mode']!='HYBRID'
            or obj['test_keys_only'] is not True or obj['release_authorized'] is not False
            or obj['plan_sha256']!=pin or type(obj['records']) is not list
            or type(obj['details']) is not list or len(obj['records'])!=1800 or len(obj['details'])!=1800):
        raise ValueError('complete reference execution required')
    configs = {c.name:c for c in plan.configurations}
    details = {}
    for d in obj['details']:
        if (type(d) is not dict or type(d.get('configuration')) is not str
                or d['configuration'] not in configs or type(d.get('seed')) is not int
                or d['seed'] not in plan.seeds or type(d.get('correct')) is not int
                or d.get('suite')!=configs[d['configuration']].suite):
            raise ValueError('invalid detail identity')
        key = (d['configuration'],d['seed'])
        if key in details:
            raise ValueError('duplicate run detail')
        details[key] = d
    runs = []
    for r in obj['records']:
        if type(r) is not dict or set(r)!={'configuration','seed','status','correct','evidence_sha256'}:
            raise ValueError('invalid run record')
        run = Run(**r)
        d = details.get((run.configuration,run.seed))
        if d is None or d['correct']!=run.correct or _digest(d)!=run.evidence_sha256:
            raise ValueError('unbound run detail')
        runs.append(run)
    report = analyze_campaign(plan,pin,tuple(runs))
    if canonical_json(report)!=canonical_json(obj['report']):
        raise ValueError('report differs from independently recomputed aggregation')
    statement = {'schema':'omega-v74-reference-attestation-v1','plan_sha256':pin,
        'execution_sha256':sha256(raw).hexdigest(),'report_sha256':_digest(report),
        'records_sha256':report['records_sha256'],'recorded':report['recorded'],
        'missing':report['missing'],'failed':report['failed'],'test_keys_only':True,
        'source_reproduction_verified':False,'release_authorized':False}
    leaves = (leaf_hash(anchor),)+tuple(leaf_hash(canonical_json({'kind':'v74-run','run':asdict(r)}))
        for r in sorted(runs,key=lambda r:(r.configuration,r.seed)))
    return statement,leaves


def _public(key):
    if not isinstance(key,Ed25519PrivateKey):
        raise ValueError('native signing key required')
    return key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)


def attest(raw: bytes, plan: CampaignPlan, pin: str, scope: ReceiptScope,
           report_signer: Ed25519PrivateKey, log_signer: Ed25519PrivateKey, *, origin: str) -> dict:
    if _public(report_signer)==_public(log_signer):
        raise ValueError('independent report and log keys required')
    statement,leaves = _material(raw,plan,pin,scope)
    receipt = sign_receipt(statement,scope,report_signer)
    leaves += (leaf_hash(canonical_json({'statement':statement,'receipt':receipt})),)
    note = sign_note(Checkpoint(origin,len(leaves),merkle_root(leaves)),origin,log_signer)
    return {'statement':statement,'receipt':receipt,'tree_size':len(leaves),'checkpoint':note.decode('utf-8'),
            'consistency':[x.hex() for x in consistency_proof(leaves,1)],
            'inclusion':[x.hex() for x in inclusion_proof(leaves,len(leaves)-1)]}


def _proof(value):
    if type(value) is not list or len(value)>64 or any(type(x) is not str or not _HEX.fullmatch(x) for x in value):
        raise ValueError('invalid proof encoding')
    return tuple(bytes.fromhex(x) for x in value)


def verify_attestation(raw: bytes, plan: CampaignPlan, pin: str, bundle: dict, *,
                       scope: ReceiptScope, receipt_key: bytes, log_key: bytes, origin: str) -> bool:
    try:
        if (type(raw) is not bytes or len(raw)>1024*1024 or receipt_key==log_key
                or type(bundle) is not dict or set(bundle)!={'statement','receipt','tree_size','checkpoint','consistency','inclusion'}
                or type(bundle['tree_size']) is not int or bundle['tree_size']!=1802
                or type(bundle['checkpoint']) is not str or len(bundle['checkpoint'])>1024
                or type(bundle['statement']) is not dict
                or bundle['statement'].get('execution_sha256')!=sha256(raw).hexdigest()):
            return False
        proof,inc = _proof(bundle['consistency']),_proof(bundle['inclusion'])
        if not verify_receipt(bundle['receipt'],bundle['statement'],scope,receipt_key):
            return False
        anchor = _context(plan,pin,scope)
        statement,leaves = _material(raw,plan,pin,scope)
        if canonical_json(statement)!=canonical_json(bundle['statement']):
            return False
        final = canonical_json({'statement':statement,'receipt':bundle['receipt']})
        leaves += (leaf_hash(final),)
        chain = CheckpointChain(Checkpoint(origin,1,leaf_hash(anchor)),key_name=origin,public_key=log_key)
        return (chain.advance(bundle['checkpoint'].encode('utf-8'),proof)=='ADVANCED'
                and chain.current.tree_size==len(leaves) and chain.current.root==merkle_root(leaves)
                and chain.includes(final,len(leaves)-1,inc))
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return False
