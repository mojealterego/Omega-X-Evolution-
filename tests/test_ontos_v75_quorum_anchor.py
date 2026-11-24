"""The actual v75 review commitment through an operator-selected quorum."""
from dataclasses import replace

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_quorum import QuorumPolicy, QuorumWitness, QuorumCertificate
from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v75_anchor import (
    AnchorEvidence, AnchorTrust, QuorumAnchorTrust, QuorumAnchorEvidence,
    review_leaf, verify_review_anchor, GATE_IDS,
)

LOG, EVAL, *WITNESSES = [Ed25519PrivateKey.from_private_bytes(bytes([i])*32) for i in range(51,57)]
ORIGIN='omega/l12-quorum-review'
CH=b'f'*32


def pub(key): return key.public_key().public_bytes_raw()


def make(tmp_path):
    trust={g:(ReceiptScope('L12',g,'a'*40,'tenant','eval'),pub(EVAL)) for g in GATE_IDS}
    receipts={g:sign_receipt({'decision':'fixture'},scope,EVAL) for g,(scope,_) in trust.items()}
    args=dict(commit_sha='a'*40,tenant='tenant',manifest_pin='b'*64,campaign_pin='c'*64,trust=trust,receipts=receipts)
    data=review_leaf(**args)
    p=QuorumPolicy('operational',ORIGIN,ORIGIN,pub(LOG),0,tuple(sorted(map(pub,WITNESSES))))
    leaves=(leaf_hash(b'prior'),leaf_hash(data))
    prior=Checkpoint(ORIGIN,1,merkle_root(leaves[:1]))
    genesis=sign_note(prior,ORIGIN,LOG)
    n=sign_note(Checkpoint(ORIGIN,2,merkle_root(leaves)),ORIGIN,LOG)
    nodes=[QuorumWitness.initialize(tmp_path/f'w{i}.db',p,k,genesis) for i,k in enumerate(WITNESSES)]
    previous=nodes[0].current(b'p'*32).receipt
    proof=consistency_proof(leaves,1)
    votes=tuple(w.vote(n,proof,expected_revision=0,challenge=CH) for w in nodes[:3])
    assert all(v is not None for v in votes)
    cert=QuorumCertificate(n,votes,proof)
    return data,QuorumAnchorTrust(p,prior,CH),QuorumAnchorEvidence(cert,inclusion_proof(leaves,1)),args,nodes,previous


def test_actual_v75_leaf_and_no_downgrade(tmp_path):
    data,t,e,args,nodes,previous=make(tmp_path)
    keys=(pub(EVAL),)
    assert verify_review_anchor(data,t,e,keys)
    assert not verify_review_anchor(data,t,replace(e,certificate=replace(e.certificate,votes=e.certificate.votes[:2])),keys)
    single=AnchorEvidence(e.certificate.votes[0].receipt,e.certificate.consistency,e.inclusion)
    assert not verify_review_anchor(data,t,single,keys)
    assert not verify_review_anchor(data,AnchorTrust(t.policy.member(pub(WITNESSES[0])),previous,CH),e,keys)
    assert not verify_review_anchor(data,replace(t,challenge=b'x'*32),e,keys)
    assert not verify_review_anchor(data,t,e,(t.policy.log_key,))
    for g in GATE_IDS:
        mutated=dict(args['receipts']); mutated[g]=sign_receipt({'decision':'changed'},args['trust'][g][0],EVAL)
        assert not verify_review_anchor(review_leaf(**{**args,'receipts':mutated}),t,e,keys)


def test_full_reducer_respects_operator_selected_quorum(tmp_path):
    # Synthetic complete evidence tests the admission protocol, not L12 acceptance.
    from dataclasses import asdict
    from hashlib import sha256
    from omega_x_evolution.ontos_v49_manifest import SOURCE_PATHS, SourceRecord, audit_inventory
    from omega_x_evolution.ontos_v72_jcs import canonical_json
    from omega_x_evolution.ontos_v72_evidence import ArtifactBundle
    from omega_x_evolution.ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign
    from omega_x_evolution.ontos_v75_acceptance import audit_l12, GateEvidence, gate_provenance
    def sha(b): return sha256(b).hexdigest()
    payloads={path:path.encode() for path in SOURCE_PATHS}
    records=tuple(SourceRecord(path,sha(payloads[path]),'REUSE','Synthetic test fixture only.','MIT') for path in SOURCE_PATHS)
    raw=canonical_json({'schema':'ontos-source-register-v49-v1','entries':[asdict(r) for r in records],
                        'entry_digest_sha256':audit_inventory(records,payloads)['manifest_sha256']})
    configs=tuple(Configuration(f'c{i:02}','ABCD'[i%4],'PRIMARY' if i<36 else 'ABLATION','FIXTURE',1,sha(str(i).encode())) for i in range(60))
    plan=CampaignPlan(tuple(range(30)),configs,(('c04','c00'),),7412,'a'*64)
    details=[{'configuration':c.name,'seed':s,'suite':c.suite,'correct':1} for c in configs for s in plan.seeds]
    runs=tuple(Run(d['configuration'],d['seed'],'COMPLETED',1,sha(canonical_json(d))) for d in details)
    campaign=canonical_json({'schema':'omega-v75-source-execution-v1','source_reproduction_verified':True,'test_keys_only':False,
        'plan':{'seeds':list(plan.seeds),'configurations':[c.body() for c in configs],'comparisons':[list(x) for x in plan.comparisons],
                'analysis_seed':plan.analysis_seed,'protocol_sha256':plan.protocol_sha256},'plan_sha256':plan.digest(),
        'records':[asdict(r) for r in runs],'details':details,'report':analyze_campaign(plan,plan.digest(),runs)})
    commit='a'*40; tenant='tenant'; manifest_pin=sha(raw); campaign_pin=sha(campaign)
    trust={g:(ReceiptScope('L12',g,commit,tenant,'eval'),pub(EVAL)) for g in GATE_IDS}
    submissions={}
    for g,(scope,_) in trust.items():
        provenance=gate_provenance(scope,manifest_pin,campaign_pin)
        replay=campaign if g in ('GATE-04','GATE-05') else b'recovery fixture' if g=='GATE-07' else None
        artifact=ArtifactBundle(b'fixture source',b'fixture log',provenance,replay)
        record={'identity':{'package_id':'L12-04/GATE','commit_sha':commit,'source_sha256':sha(artifact.source),'timestamp_utc':'2026-11-24T00:00:00Z'},
                'contract':{'version':'omega-v75-gate-v1','assumptions':[],'preconditions':[],'domain':'L12-full','rights':[],'tenant':tenant},
                'environment':{'os':'fixture','hardware':'fixture','compiler_or_runtime':'fixture','solver':None,'pinned_dependencies':{}},
                'test':{'test_id':'L12/'+g,'seed':0,'command':'fixture','start_state':'fixture','exit_code':0,'log_sha256':sha(artifact.log)},
                'verification':{'mode':'DETERMINISTIC-SIMULATION','model_limitations':['Fixture only']},
                'fault_model':{'injection_schedule':[],'retries':0,'crash_restart_tested':g=='GATE-07','replay_artifact_sha256':sha(replay) if replay else None},
                'metrics':{'correctness':None,'latency_p95_ms':None,'latency_p99_ms':None,'memory_mib':None,'energy_joules':None,'provenance_sha256':sha(provenance)},
                'decision':{'status':'PASS','reason':'Test fixture only'},
                'promotion':{'operator_approval_required':False,'operator_approval_id':None,'rollback_ref':commit,'regression_ref':None}}
        submissions[g]=GateEvidence(record,sign_receipt(record,scope,EVAL),artifact)
    data=review_leaf(commit_sha=commit,tenant=tenant,manifest_pin=manifest_pin,campaign_pin=campaign_pin,
                     trust=trust,receipts={g:e.receipt for g,e in submissions.items()})
    p=QuorumPolicy('operational',ORIGIN,ORIGIN,pub(LOG),0,tuple(sorted(map(pub,WITNESSES))))
    leaves=(leaf_hash(b'prior'),leaf_hash(data)); prior=Checkpoint(ORIGIN,1,merkle_root(leaves[:1]))
    genesis=sign_note(prior,ORIGIN,LOG); n=sign_note(Checkpoint(ORIGIN,2,merkle_root(leaves)),ORIGIN,LOG)
    nodes=[QuorumWitness.initialize(tmp_path/f'v{i}.db',p,k,genesis) for i,k in enumerate(WITNESSES)]
    proof=consistency_proof(leaves,1)
    votes=tuple(w.vote(n,proof,expected_revision=0,challenge=CH) for w in nodes[:3])
    assert all(v is not None for v in votes)
    anchor=QuorumAnchorTrust(p,prior,CH)
    cert=QuorumAnchorEvidence(QuorumCertificate(n,votes,proof),inclusion_proof(leaves,1))
    def audit(evidence):
        return audit_l12(raw,manifest_pin,payloads,commit_sha=commit,tenant=tenant,source_campaign_sha256=campaign_pin,
                         trust=trust,submissions=submissions,anchor_trust=anchor,anchor_evidence=evidence)
    result=audit(cert)
    assert result['gates']['GATE-09']=='PASS' and result['release_authorized'] is False
    assert audit(replace(cert,certificate=replace(cert.certificate,votes=votes[:2])))['gates']['GATE-09']=='FAIL'
    assert audit(None)['gates']['GATE-09']=='BLOCKED'
    assert audit(AnchorEvidence(votes[0].receipt,proof,cert.inclusion))['gates']['GATE-09']=='FAIL'
    submissions.pop('GATE-06')
    assert audit(cert)['gates']['GATE-09']=='BLOCKED'
