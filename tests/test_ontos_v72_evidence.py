"""Section 10 schema, authenticated scope and actual artifact binding."""
import copy
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v72_evidence import ArtifactBundle, validate_record, verify_record

KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC = KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
SCOPE = ReceiptScope('L12', 'GATE-04', 'a'*40, 'tenant-1', 'eval-1')
ARTIFACTS = ArtifactBundle(b'source fixture', b'test log fixture', b'provenance fixture', b'replay fixture')


def digest(data): return hashlib.sha256(data).hexdigest()


def record():
    return {
        'identity': {'package_id':'L12-03/TEST','commit_sha':'a'*40,'source_sha256':digest(ARTIFACTS.source),'timestamp_utc':'2026-11-24T00:00:00Z'},
        'contract': {'version':'1','assumptions':[],'preconditions':[],'domain':'TRUST','rights':['read-only'],'tenant':'tenant-1'},
        'environment': {'os':'Linux','hardware':'fixture','compiler_or_runtime':'CPython','solver':None,'pinned_dependencies':{'cryptography':'46.0.4'}},
        'test': {'test_id':'test-01','seed':72,'command':'pytest','start_state':'clean','exit_code':0,'log_sha256':digest(ARTIFACTS.log)},
        'verification': {'mode':'DETERMINISTIC-SIMULATION','model_limitations':['finite model']},
        'fault_model': {'injection_schedule':['restart'],'retries':0,'crash_restart_tested':True,'replay_artifact_sha256':digest(ARTIFACTS.replay)},
        'metrics': {'correctness':1.,'latency_p95_ms':1.,'latency_p99_ms':2.,'memory_mib':None,'energy_joules':None,'provenance_sha256':digest(ARTIFACTS.provenance)},
        'decision': {'status':'PASS','reason':'fixture only'},
        'promotion': {'operator_approval_required':False,'operator_approval_id':None,'rollback_ref':'b'*40,'regression_ref':None},
    }


def test_valid_record_authenticates_but_does_not_promote():
    r = record()
    validate_record(r)
    result = verify_record(r, sign_receipt(r,SCOPE,KEY), SCOPE, PUBLIC, ARTIFACTS)
    assert result['authenticated'] is True
    assert result['record_status'] == 'PASS'
    assert result['release_authorized'] is False


@pytest.mark.parametrize('section', tuple(record()))
def test_every_section_required(section):
    r = record(); del r[section]
    with pytest.raises(ValueError): validate_record(r)


@pytest.mark.parametrize('section,field,value', [
    ('identity','package_id','L12-01/TEST'), ('identity','commit_sha','z'*40),
    ('identity','timestamp_utc','2026-02-30T00:00:00Z'), ('contract','rights','read-only'),
    ('environment','pinned_dependencies',{'x':1}), ('test','exit_code',True),
    ('test','exit_code',1), ('test','seed',True), ('verification','mode','DEPLOYED'),
    ('verification','model_limitations',[]), ('fault_model','retries',-1),
    ('fault_model','crash_restart_tested',1), ('fault_model','replay_artifact_sha256',None),
    ('metrics','correctness',1.1), ('metrics','latency_p99_ms',0.5),
    ('metrics','energy_joules',float('nan')), ('decision','status','GREEN'),
    ('promotion','operator_approval_required',True), ('promotion','rollback_ref',''),
    ('test','extra','unexpected'),
])
def test_invalid_fields_and_semantics(section,field,value):
    r = record(); r[section][field] = value
    with pytest.raises(ValueError): validate_record(r)


@pytest.mark.parametrize('field', ['source','log','provenance','replay'])
def test_actual_artifacts_must_match(field):
    r = record()
    args = dict(source=ARTIFACTS.source,log=ARTIFACTS.log,provenance=ARTIFACTS.provenance,replay=ARTIFACTS.replay)
    args[field] = b'wrong artifact'
    result = verify_record(r,sign_receipt(r,SCOPE,KEY),SCOPE,PUBLIC,ArtifactBundle(**args))
    assert result['authenticated'] is False and result['release_authorized'] is False


@pytest.mark.parametrize('section,field,value', [('identity','commit_sha','b'*40),('identity','package_id','L13-03/TEST'),('contract','tenant','tenant-2')])
def test_signed_record_cannot_disagree_with_receipt_scope(section,field,value):
    r = record(); r[section][field] = value
    result = verify_record(r, sign_receipt(r,SCOPE,KEY), SCOPE, PUBLIC, ARTIFACTS)
    assert result['authenticated'] is False


def test_invalid_signed_record_and_nonpass_authentication():
    r = record(); r['test']['exit_code'] = 1
    receipt = sign_receipt(r,SCOPE,KEY)
    assert verify_record(r,receipt,SCOPE,PUBLIC,ARTIFACTS)['authenticated'] is False
    r['decision']['status'] = 'FAIL'
    result = verify_record(r,sign_receipt(r,SCOPE,KEY),SCOPE,PUBLIC,ARTIFACTS)
    assert result['authenticated'] is True and result['record_status'] == 'FAIL'
    assert not result['release_authorized']


def test_artifact_bounds_and_optional_replay():
    with pytest.raises(ValueError): ArtifactBundle(b'',b'x',b'x')
    with pytest.raises(ValueError): ArtifactBundle(b'x'*(16*1024*1024+1),b'x',b'x')
    r = record(); r['fault_model']['crash_restart_tested'] = False
    r['fault_model']['replay_artifact_sha256'] = None
    a = ArtifactBundle(ARTIFACTS.source, ARTIFACTS.log, ARTIFACTS.provenance)
    assert verify_record(r,sign_receipt(r,SCOPE,KEY),SCOPE,PUBLIC,a)['authenticated']
    assert not verify_record(r,sign_receipt(r,SCOPE,KEY),SCOPE,PUBLIC,ARTIFACTS)['authenticated']
