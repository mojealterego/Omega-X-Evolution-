import copy
from dataclasses import asdict, replace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_v72_receipts import ReceiptScope
from omega_x_evolution.ontos_v74_campaign import Run, analyze_campaign
from omega_x_evolution.ontos_v74_reference import reference_plan, digest
from omega_x_evolution.ontos_v74_attestation import attest, verify_attestation

R = Ed25519PrivateKey.from_private_bytes(bytes([41])*32)
L = Ed25519PrivateKey.from_private_bytes(bytes([42])*32)
SCOPE = ReceiptScope('L12','GATE-04','a'*40,'reference','fixture')
ORIGIN = 'omega-reference/log'


def pub(key):
    return key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)


@pytest.fixture(scope='module')
def fixture():
    p = reference_plan()
    details = [{'configuration':c.name,'seed':s,'suite':c.suite,'correct':1}
               for c in p.configurations for s in p.seeds]
    runs = tuple(Run(d['configuration'],d['seed'],'COMPLETED',1,digest(d)) for d in details)
    obj = {'schema':'omega-v74-reference-execution-v1','verification_mode':'HYBRID',
           'test_keys_only':True,'plan_sha256':p.digest(),'report':analyze_campaign(p,p.digest(),runs),
           'records':[asdict(r) for r in runs],'details':details,'release_authorized':False}
    raw = canonical_json(obj)
    return p,raw,attest(raw,p,p.digest(),SCOPE,R,L,origin=ORIGIN)


def verify(p,raw,bundle,**changes):
    args = dict(scope=SCOPE,receipt_key=pub(R),log_key=pub(L),origin=ORIGIN)
    args.update(changes)
    return verify_attestation(raw,p,p.digest(),bundle,**args)


def test_signed_report_and_merkle_history(fixture):
    p,raw,bundle = fixture
    assert verify(p,raw,bundle)
    assert bundle['statement']['recorded']==1800
    assert bundle['statement']['test_keys_only'] is True
    assert bundle['statement']['release_authorized'] is False
    assert bundle['tree_size']==1802


def test_tamper_and_wrong_trust(fixture):
    p,raw,bundle = fixture
    assert not verify(p,raw+b'\n',bundle)
    assert not verify(p,raw,bundle,receipt_key=pub(L))
    assert not verify(p,raw,bundle,scope=replace(SCOPE,commit_sha='b'*40))
    for field in ('checkpoint','consistency','inclusion','receipt','statement','tree_size'):
        b = copy.deepcopy(bundle); b[field] = None
        assert not verify(p,raw,b)


def test_issuer_rejects_unbound_detail_and_report(fixture):
    from omega_x_evolution.ontos_v72_jcs import parse_json
    p,raw,_ = fixture
    obj = parse_json(raw); obj['details'][0]['correct']=2
    with pytest.raises(ValueError): attest(canonical_json(obj),p,p.digest(),SCOPE,R,L,origin=ORIGIN)
    obj = parse_json(raw); obj['report']['recorded']=1799
    with pytest.raises(ValueError): attest(canonical_json(obj),p,p.digest(),SCOPE,R,L,origin=ORIGIN)
    with pytest.raises(ValueError): attest(raw,p,p.digest(),SCOPE,R,R,origin=ORIGIN)
