"""One-shot blind holdout admission and aggregate-only release."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v73_holdout import (
    Candidate, HoldoutPlan, HoldoutBroker, label_commitment, submission_bytes, seal_bytes,
)

A, B, EXT = (Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in (1,2,3))
TRUTH = (1,0,1,0)
SALT = bytes(range(32))


def pub(key):
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def plan(*, truth=TRUTH, salt=SALT, campaign='run-1'):
    return HoldoutPlan('tenant-a',campaign,'a'*64,'b'*64,len(truth),
                       label_commitment(truth,salt),
                       (Candidate('a','c'*64,pub(A)),Candidate('b','d'*64,pub(B))),pub(EXT))


def broker(p=None, truth=TRUTH, salt=SALT):
    return HoldoutBroker(p or plan(),truth,salt)


def submit(b, name, values, key):
    return b.submit(name,values,key.sign(submission_bytes(b.plan_digest,name,values)))


def seal(b):
    return b.seal(EXT.sign(seal_bytes(b.plan_digest)))


def test_blind_until_seal_and_exact_aggregate():
    b = broker()
    assert b.report() is None
    assert submit(b,'a',(1,0,None,1),A) == 'ACCEPTED'
    assert b.report() is None
    assert submit(b,'b',(1,0,1,0),B) == 'ACCEPTED'
    assert b.report() is None
    assert seal(b) == 'SEALED'
    r = b.report()
    assert r['candidates']['a'] == {'status':'SCORED','correct':2,'incorrect':1,'abstained':1,'total':4}
    assert r['candidates']['b']['correct'] == 4
    assert r['release_authorized'] is False
    assert 'truth' not in r and 'predictions' not in r
    r['candidates']['a']['correct'] = 999
    assert b.report()['candidates']['a']['correct'] == 2


def test_manifest_binding_candidate_and_campaign():
    b = broker(); other = broker(plan(campaign='run-2'))
    values = (1,0,1,0)
    sig = A.sign(submission_bytes(b.plan_digest,'a',values))
    assert other.submit('a',values,sig) == 'REJECTED'
    assert b.submit('b',values,sig) == 'REJECTED'
    assert b.submit('a',(0,0,1,0),sig) == 'REJECTED'
    assert submit(b,'a',values,B) == 'REJECTED'
    assert b.submit('a',values,sig) == 'ACCEPTED'


def test_no_requery_and_concurrent_submission():
    b = broker(); values = (1,0,1,0)
    sig = A.sign(submission_bytes(b.plan_digest,'a',values))
    with ThreadPoolExecutor(max_workers=2) as ex:
        outcomes = list(ex.map(lambda _:b.submit('a',values,sig),range(2)))
    assert sorted(outcomes) == ['ACCEPTED','REJECTED']
    assert submit(b,'a',(0,0,0,0),A) == 'REJECTED'
    assert b.report() is None


def test_only_external_authority_seals_and_missing_is_failure():
    b = broker()
    assert b.seal(A.sign(seal_bytes(b.plan_digest))) == 'REJECTED'
    assert b.report() is None
    assert seal(b) == 'SEALED'
    assert seal(b) == 'SEALED'
    assert b.report()['candidates']['a'] == {'status':'MISSING','correct':0,'incorrect':0,'abstained':4,'total':4}
    assert submit(b,'a',TRUTH,A) == 'REJECTED'


def test_commitment_and_salt_validation():
    with pytest.raises(ValueError): broker(truth=(0,0,0,0))
    with pytest.raises(ValueError): broker(salt=bytes(32))
    with pytest.raises(ValueError): label_commitment(TRUTH,b'x')
    assert label_commitment(TRUTH,SALT) != label_commitment(TRUTH,bytes(32))


@pytest.mark.parametrize('values', [(True,0,1,0),(2,0,1,0),(1,0,1),[1,0,1,0],(1,0,1,0,0)])
def test_invalid_prediction_contract(values):
    b = broker()
    assert b.submit('a',values,bytes(64)) == 'REJECTED'
    assert b.report() is None
    assert submit(b,'a',TRUTH,A) == 'ACCEPTED'


def test_no_score_side_channel_in_admission_transcript():
    a = broker(); other_truth = (0,1,0,1)
    b = broker(plan(truth=other_truth),other_truth)
    for g in (a,b):
        assert submit(g,'a',TRUTH,A) == 'ACCEPTED'
        assert submit(g,'a',TRUTH,A) == 'REJECTED'
        assert g.report() is None
        assert seal(g) == 'SEALED'
    assert a.report()['candidates']['a']['correct'] == 4
    assert b.report()['candidates']['a']['correct'] == 0


def test_invalid_manifest_rejects_conflicting_keys_and_identity():
    p = plan()
    with pytest.raises(ValueError): HoldoutPlan(p.tenant,p.campaign,p.protocol_sha256,p.features_sha256,4,p.labels_commitment,(p.candidates[0],Candidate('b','d'*64,pub(A))),pub(EXT))
    with pytest.raises(ValueError): HoldoutPlan(p.tenant,p.campaign,p.protocol_sha256,p.features_sha256,4,p.labels_commitment,p.candidates,pub(A))
    with pytest.raises(ValueError): Candidate('../x','a'*64,pub(A))
    with pytest.raises(ValueError): Candidate('a','a'*64,bytes(32))
