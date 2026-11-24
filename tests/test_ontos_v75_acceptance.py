from dataclasses import asdict
from hashlib import sha256

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from omega_x_evolution.ontos_v49_manifest import SOURCE_PATHS, SourceRecord, audit_inventory
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_v72_evidence import ArtifactBundle
from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v75_acceptance import verify_manifest, audit_l12, GateEvidence, gate_provenance, GATES
from omega_x_evolution.ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign

COMMIT='a'*40
KEY=Ed25519PrivateKey.from_private_bytes(bytes([71])*32)
PUBLIC=KEY.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)


def sha(data):
    return sha256(data).hexdigest()


def manifest(complete=True):
    payloads={p:p.encode() for p in SOURCE_PATHS} if complete else {}
    records=tuple(SourceRecord(p,sha(payloads[p]) if complete else None,
        'REUSE' if complete else 'RESEARCH','Explicit test fixture only.',
        'MIT' if complete else 'UNKNOWN') for p in SOURCE_PATHS)
    body={'schema':'ontos-source-register-v49-v1','entries':[asdict(r) for r in records],
          'entry_digest_sha256':audit_inventory(records,payloads)['manifest_sha256']}
    return canonical_json(body),payloads


def evidence(gate,manifest_pin,campaign,*,status='PASS',domain='L12-full'):
    scope=ReceiptScope('L12',gate,COMMIT,'fixture','reviewer')
    provenance=gate_provenance(scope,manifest_pin,sha(campaign) if campaign else None)
    replay=campaign if gate in ('GATE-04','GATE-05') else b'recovery fixture' if gate=='GATE-07' else None
    bundle=ArtifactBundle(b'fixture source',b'fixture log',provenance,replay)
    record={'identity':{'package_id':'L12-04/GATE','commit_sha':COMMIT,'source_sha256':sha(bundle.source),'timestamp_utc':'2026-11-24T00:00:00Z'},
            'contract':{'version':'omega-v75-gate-v1','assumptions':[],'preconditions':[],'domain':domain,'rights':[],'tenant':'fixture'},
            'environment':{'os':'fixture','hardware':'fixture','compiler_or_runtime':'fixture','solver':None,'pinned_dependencies':{}},
            'test':{'test_id':'L12/'+gate,'seed':0,'command':'fixture','start_state':'fixture','exit_code':0,'log_sha256':sha(bundle.log)},
            'verification':{'mode':'DETERMINISTIC-SIMULATION','model_limitations':['Unit test only']},
            'fault_model':{'injection_schedule':[],'retries':0,'crash_restart_tested':gate=='GATE-07','replay_artifact_sha256':sha(replay) if replay else None},
            'metrics':{'correctness':None,'latency_p95_ms':None,'latency_p99_ms':None,'memory_mib':None,'energy_joules':None,'provenance_sha256':sha(provenance)},
            'decision':{'status':status,'reason':'Unit fixture, not a real gate result'},
            'promotion':{'operator_approval_required':False,'operator_approval_id':None,'rollback_ref':COMMIT,'regression_ref':None}}
    return (scope,PUBLIC),GateEvidence(record,sign_receipt(record,scope,KEY),bundle)


def run(raw,payloads,trust,submissions,campaign=None):
    return audit_l12(raw,sha(raw),payloads,commit_sha=COMMIT,tenant='fixture',
                     source_campaign_sha256=sha(campaign) if campaign else None,
                     trust=trust,submissions=submissions)


def test_manifest_structure_is_not_byte_verification():
    raw,payloads=manifest(False)
    r=verify_manifest(raw,sha(raw),payloads)
    assert r['registered']==33 and r['checked_blobs']==0 and r['status']=='BLOCKED'
    assert r['inventory_verified'] is True


def test_manifest_all_bytes_and_wrong_digest():
    raw,payloads=manifest()
    assert verify_manifest(raw,sha(raw),payloads)['status']=='PASS'
    assert verify_manifest(raw,'0'*64,payloads)['status']=='FAIL'
    payloads[SOURCE_PATHS[0]]=b'changed'
    assert verify_manifest(raw,sha(raw),payloads)['status']=='FAIL'


def test_missing_gates_never_pass():
    raw,payloads=manifest(False)
    r=run(raw,payloads,{}, {})
    assert r['gates']['GATE-09']=='BLOCKED'
    assert all(v=='BLOCKED' for v in r['gates'].values())
    assert r['release_authorized'] is False


def source_fixture():
    configs=tuple(Configuration(f'c{i:02}','ABCD'[i%4],'PRIMARY' if i<36 else 'ABLATION','SOURCE-FIXTURE',1,sha(str(i).encode())) for i in range(60))
    p=CampaignPlan(tuple(range(30)),configs,(('c04','c00'),),7412,'a'*64)
    details=[{'configuration':c.name,'seed':seed,'suite':c.suite,'correct':1} for c in configs for seed in p.seeds]
    runs=tuple(Run(d['configuration'],d['seed'],'COMPLETED',1,sha(canonical_json(d))) for d in details)
    return canonical_json({'schema':'omega-v75-source-execution-v1','source_reproduction_verified':True,'test_keys_only':False,
        'plan':{'seeds':list(p.seeds),'configurations':[c.body() for c in configs],
                'comparisons':[list(x) for x in p.comparisons],'analysis_seed':p.analysis_seed,'protocol_sha256':p.protocol_sha256},
        'plan_sha256':p.digest(),'records':[asdict(r) for r in runs],'details':details,'report':analyze_campaign(p,p.digest(),runs)})


def test_all_evidence_required_reducer_fixture():
    raw,payloads=manifest(); campaign=source_fixture()
    pairs={g:evidence(g,sha(raw),campaign) for g in GATES}
    trust={g:p[0] for g,p in pairs.items()}; submissions={g:p[1] for g,p in pairs.items()}
    r=run(raw,payloads,trust,submissions,campaign)
    assert r['gates']['GATE-09']=='BLOCKED' and r['release_authorized'] is False
    assert r['anchor_status']=='BLOCKED' and all(r['gates'][g]=='PASS' for g in GATES)
    submissions.pop('GATE-06')
    assert run(raw,payloads,trust,submissions,campaign)['gates']['GATE-09']=='BLOCKED'


def test_reference_campaign_cannot_satisfy_full_gates():
    raw,payloads=manifest(); campaign=canonical_json({'schema':'omega-v74-reference-execution-v1','test_keys_only':True,'source_reproduction_verified':False})
    trust,sub=evidence('GATE-04',sha(raw),campaign)
    r=run(raw,payloads,{'GATE-04':trust},{'GATE-04':sub},campaign)
    assert r['gates']['GATE-04']=='FAIL' and r['gates']['GATE-09']=='FAIL'


def test_bad_signature_wrong_domain_and_not_applicable():
    raw,payloads=manifest()
    trust,sub=evidence('GATE-06',sha(raw),None,domain='reference')
    assert run(raw,payloads,{'GATE-06':trust},{'GATE-06':sub})['gates']['GATE-06']=='FAIL'
    trust,sub=evidence('GATE-06',sha(raw),None,status='NOT_APPLICABLE')
    assert run(raw,payloads,{'GATE-06':trust},{'GATE-06':sub})['gates']['GATE-06']=='BLOCKED'
    sub.receipt['signature_hex']='0'*128
    assert run(raw,payloads,{'GATE-06':trust},{'GATE-06':sub})['gates']['GATE-06']=='FAIL'


def test_signed_source_marker_without_complete_records_rejected():
    raw,payloads=manifest(); campaign=canonical_json({'source_reproduction_verified':True,'test_keys_only':False})
    trust,sub=evidence('GATE-04',sha(raw),campaign)
    assert run(raw,payloads,{'GATE-04':trust},{'GATE-04':sub},campaign)['gates']['GATE-04']=='FAIL'


def test_final_gate_requires_exact_fresh_witness_tip(tmp_path):
    from dataclasses import replace
    from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
    from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
    from omega_x_evolution.ontos_v72_witness import WitnessPolicy, WitnessStore
    from omega_x_evolution.ontos_v75_anchor import AnchorTrust, AnchorEvidence, review_leaf
    raw,payloads=manifest(); campaign=source_fixture()
    pairs={g:evidence(g,sha(raw),campaign) for g in GATES}
    trust={g:p[0] for g,p in pairs.items()}; submissions={g:p[1] for g,p in pairs.items()}
    # Public fixture keys exercise the operational-authority protocol only.
    log=Ed25519PrivateKey.from_private_bytes(bytes([72])*32)
    signer=Ed25519PrivateKey.from_private_bytes(bytes([73])*32)
    origin='omega/l12-fixture'
    policy=WitnessPolicy('operational',origin,origin,log.public_key().public_bytes_raw(),signer.public_key().public_bytes_raw())
    leaf=review_leaf(commit_sha=COMMIT,tenant='fixture',manifest_pin=sha(raw),campaign_pin=sha(campaign),
                     trust=trust,receipts={g:s.receipt for g,s in submissions.items()})
    leaves=(leaf_hash(b'genesis'),leaf_hash(leaf))
    def note(items):
        return sign_note(Checkpoint(origin,len(items),merkle_root(items)),origin,log)
    store=WitnessStore.initialize(tmp_path/'review.sqlite',policy,signer,note(leaves[:1]))
    previous=store.read(b'p'*32)
    assert store.advance(note(leaves),consistency_proof(leaves,1),expected_revision=0)=='ADVANCED'
    pin=AnchorTrust(policy,previous,b'c'*32)
    proof=AnchorEvidence(store.read(pin.challenge),consistency_proof(leaves,1),inclusion_proof(leaves,1))
    def audit(anchor):
        return audit_l12(raw,sha(raw),payloads,commit_sha=COMMIT,tenant='fixture',source_campaign_sha256=sha(campaign),
                         trust=trust,submissions=submissions,anchor_trust=pin,anchor_evidence=anchor)
    assert audit(proof)['gates']['GATE-09']=='PASS'
    assert audit(proof)['release_authorized'] is False
    assert audit(replace(proof,inclusion=()))['gates']['GATE-09']=='FAIL'
    assert audit(None)['gates']['GATE-09']=='BLOCKED'
    # Another authentic PASS receipt for the same gate is not the anchored review.
    item=submissions['GATE-02']; record={**item.record,'decision':{'status':'PASS','reason':'Different signed fixture'}}
    submissions['GATE-02']=GateEvidence(record,sign_receipt(record,trust['GATE-02'][0],KEY),item.artifacts)
    r=audit(proof)
    assert all(r['gates'][g]=='PASS' for g in GATES) and r['gates']['GATE-09']=='FAIL'
