"""Actual reducer and SQLite integration, deliberately synthetic L12 source fixture."""
from dataclasses import asdict, replace
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
import shutil
from io import BytesIO
from zipfile import ZipFile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from omega_x_evolution.ontos_v49_manifest import SOURCE_PATHS, SourceRecord, audit_inventory
from omega_x_evolution.ontos_v72_jcs import canonical_json
from omega_x_evolution.ontos_v72_evidence import ArtifactBundle
from omega_x_evolution.ontos_v72_receipts import ReceiptScope, sign_receipt
from omega_x_evolution.ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign
from omega_x_evolution.ontos_v75_acceptance import audit_l12, GateEvidence, GATES, gate_provenance, JournalQuorumAnchorTrust
from omega_x_evolution.ontos_v75_anchor import review_leaf, QuorumAnchorEvidence, QuorumAnchorTrust, AnchorEvidence
from omega_x_evolution.ontos_v75_manifest import SourceArchive
from omega_x_evolution.ontos_v72_checkpoint_note import Checkpoint, sign_note
from omega_x_evolution.ontos_v72_merkle import leaf_hash, merkle_root, consistency_proof, inclusion_proof
from omega_x_evolution.ontos_v72_quorum import QuorumPolicy, QuorumWitness, QuorumCertificate
from omega_x_evolution.ontos_v72_quorum_rotation import QuorumEpochPin
from omega_x_evolution.ontos_v72_quorum_journal import QuorumEpochJournal


def sha(data):
    return sha256(data).hexdigest()


def key(n):
    return Ed25519PrivateKey.from_private_bytes(bytes([n]) * 32)


def pub(n):
    return key(n).public_key().public_bytes_raw()


COMMIT = 'a' * 40
CHALLENGE = b'v' * 32


@pytest.fixture(scope='module')
def inputs():
    payloads = {p: p.encode() for p in SOURCE_PATHS}
    records = tuple(SourceRecord(p, sha(data), 'REUSE', 'Explicit test fixture only.', 'MIT') for p, data in payloads.items())
    raw = canonical_json({'schema': 'ontos-source-register-v49-v1', 'entries': [asdict(r) for r in records],
                          'entry_digest_sha256': audit_inventory(records, payloads)['manifest_sha256']})
    configs = tuple(Configuration(f'c{i:02}', 'ABCD'[i % 4], 'PRIMARY' if i < 36 else 'ABLATION', 'SOURCE-FIXTURE', 1, sha(str(i).encode())) for i in range(60))
    plan = CampaignPlan(tuple(range(30)), configs, (('c04', 'c00'),), 7412, 'a' * 64)
    details = [{'configuration': c.name, 'seed': s, 'suite': c.suite, 'correct': 1} for c in configs for s in plan.seeds]
    runs = tuple(Run(d['configuration'], d['seed'], 'COMPLETED', 1, sha(canonical_json(d))) for d in details)
    campaign = canonical_json({'schema': 'omega-v75-source-execution-v1', 'source_reproduction_verified': True,
        'test_keys_only': False, 'plan': {'seeds': list(plan.seeds), 'configurations': [c.body() for c in configs],
        'comparisons': [list(x) for x in plan.comparisons], 'analysis_seed': plan.analysis_seed, 'protocol_sha256': plan.protocol_sha256},
        'plan_sha256': plan.digest(), 'records': [asdict(r) for r in runs], 'details': details,
        'report': analyze_campaign(plan, plan.digest(), runs)})
    trust, submissions = {}, {}
    for i, gate in enumerate(GATES):
        signer = key(i + 20)
        scope = ReceiptScope('L12', gate, COMMIT, 'fixture', 'reviewer')
        provenance = gate_provenance(scope, sha(raw), sha(campaign))
        replay = campaign if gate in ('GATE-04', 'GATE-05') else b'recovery fixture' if gate == 'GATE-07' else None
        bundle = ArtifactBundle(b'fixture source', b'fixture log', provenance, replay)
        rec = {'identity': {'package_id': 'L12-04/GATE', 'commit_sha': COMMIT, 'source_sha256': sha(bundle.source), 'timestamp_utc': '2026-11-25T00:00:00Z'},
               'contract': {'version': 'omega-v75-gate-v1', 'assumptions': [], 'preconditions': [], 'domain': 'L12-full', 'rights': [], 'tenant': 'fixture'},
               'environment': {'os': 'fixture', 'hardware': 'fixture', 'compiler_or_runtime': 'fixture', 'solver': None, 'pinned_dependencies': {}},
               'test': {'test_id': 'L12/' + gate, 'seed': 0, 'command': 'fixture', 'start_state': 'fixture', 'exit_code': 0, 'log_sha256': sha(bundle.log)},
               'verification': {'mode': 'DETERMINISTIC-SIMULATION', 'model_limitations': ['Synthetic source fixture only']},
               'fault_model': {'injection_schedule': [], 'retries': 0, 'crash_restart_tested': gate == 'GATE-07', 'replay_artifact_sha256': sha(replay) if replay else None},
               'metrics': {'correctness': None, 'latency_p95_ms': None, 'latency_p99_ms': None, 'memory_mib': None, 'energy_joules': None, 'provenance_sha256': sha(provenance)},
               'decision': {'status': 'PASS', 'reason': 'Synthetic fixture, not actual L12 acceptance'},
               'promotion': {'operator_approval_required': False, 'operator_approval_id': None, 'rollback_ref': COMMIT, 'regression_ref': None}}
        trust[gate] = (scope, pub(i + 20))
        submissions[gate] = GateEvidence(rec, sign_receipt(rec, scope, signer), bundle)
    return raw, payloads, campaign, dict(reversed(list(trust.items()))), submissions


@pytest.fixture
def anchored(tmp_path, inputs):
    tmp_path.chmod(0o700)
    raw, payloads, campaign, trust, submissions = inputs
    leaf = review_leaf(commit_sha=COMMIT, tenant='fixture', manifest_pin=sha(raw), campaign_pin=sha(campaign),
                       trust=trust, receipts={g: s.receipt for g, s in submissions.items()})
    policy = QuorumPolicy('operational', 'omega/review', 'omega/review', pub(1), 0,
                          tuple(sorted(pub(i) for i in range(3, 7))))
    leaves = (leaf_hash(b'genesis'), leaf_hash(leaf))
    base = Checkpoint(policy.origin, 1, merkle_root(leaves[:1]))
    tip = Checkpoint(policy.origin, 2, merkle_root(leaves))
    pin = QuorumEpochPin(policy, base, pub(2), b'p' * 32, ())
    note = sign_note(tip, policy.log_name, key(1))
    genesis = sign_note(base, policy.log_name, key(1))
    proof = consistency_proof(leaves, 1)
    votes = tuple(QuorumWitness.initialize(tmp_path / f'w{i}.db', policy, key(i), genesis)
                  .vote(note, proof, expected_revision=0, challenge=CHALLENGE) for i in range(3, 7))
    assert all(v is not None for v in votes)
    journal = QuorumEpochJournal.initialize(tmp_path / 'client.db', pin)
    at = JournalQuorumAnchorTrust(journal, journal.genesis, CHALLENGE)
    evidence = QuorumAnchorEvidence(QuorumCertificate(note, votes, proof), inclusion_proof(leaves, 1))
    return journal, at, evidence, pin, tip


def audit(inputs, trust, evidence, *, submissions=None, archive=False):
    raw, payloads, campaign, keys, subs = inputs
    if archive:
        buf = BytesIO()
        with ZipFile(buf, 'w') as z:
            for path, data in payloads.items():
                z.writestr(path, data)
        packed = buf.getvalue()
        payloads = SourceArchive(packed, sha(packed))
    return audit_l12(raw, sha(raw), payloads, commit_sha=COMMIT, tenant='fixture', source_campaign_sha256=sha(campaign),
                     trust=keys, submissions=subs if submissions is None else submissions,
                     anchor_trust=trust, anchor_evidence=evidence)


def test_actual_reducer_commits_and_returns_cursor(inputs, anchored, tmp_path):
    journal, at, evidence, pin, tip = anchored
    result = audit(inputs, at, evidence, archive=True)
    assert all(status == 'PASS' for status in result['gates'].values())
    assert result['release_authorized'] is False
    cursor = journal.read(journal.genesis).cursor
    assert result['anchor_cursor'] == {'sequence': cursor.sequence, 'digest': cursor.digest.hex()}
    assert QuorumEpochJournal(tmp_path / 'client.db', pin).read(cursor).state.checkpoint == tip
    stale = audit(inputs, at, evidence)
    assert stale['gates']['GATE-09'] == 'BLOCKED' and stale['anchor_cursor'] is None


def test_incomplete_gates_and_wrong_proof_do_not_mutate(inputs, anchored):
    journal, at, evidence, _, _ = anchored
    subs = dict(inputs[-1]); subs.pop('GATE-06')
    assert audit(inputs, at, evidence, submissions=subs)['gates']['GATE-09'] == 'BLOCKED'
    assert audit(inputs, at, replace(evidence, inclusion=()))['gates']['GATE-09'] == 'FAIL'
    single = AnchorEvidence(evidence.certificate.votes[0].receipt, evidence.certificate.consistency, evidence.inclusion)
    assert audit(inputs, at, single)['gates']['GATE-09'] == 'FAIL'
    assert journal.read(journal.genesis).cursor == journal.genesis


def test_legacy_anchor_unchanged_and_journal_race(inputs, anchored):
    journal, at, evidence, pin, _ = anchored
    old = audit(inputs, QuorumAnchorTrust(pin.policy, pin.checkpoint, CHALLENGE), evidence)
    assert old['gates']['GATE-09'] == 'PASS' and 'anchor_cursor' not in old
    assert journal.read(journal.genesis).cursor == journal.genesis
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: audit(inputs, at, evidence), range(2)))
    assert sorted(r['gates']['GATE-09'] for r in results) == ['BLOCKED', 'PASS']


def test_restored_client_db_and_missing_store_never_pass(inputs, anchored, tmp_path):
    from omega_x_evolution.ontos_epoch_journal_core import Cursor
    journal, at, evidence, _, _ = anchored
    path = tmp_path / 'client.db'
    backup = tmp_path / 'backup.db'
    shutil.copyfile(path, backup)
    result = audit(inputs, at, evidence)
    cursor = Cursor(result['anchor_cursor']['sequence'], bytes.fromhex(result['anchor_cursor']['digest']))
    shutil.copyfile(backup, path)
    retained = replace(at, expected=cursor)
    restored = audit(inputs, retained, evidence)
    assert restored['gates']['GATE-09'] == 'FAIL' and restored['anchor_cursor'] is None
    path.unlink()
    unavailable = audit(inputs, retained, evidence)
    assert unavailable['gates']['GATE-09'] == 'BLOCKED' and unavailable['anchor_cursor'] is None
