"""L12 full-scope evidence admission and fail-closed gate reduction.

A PASS means the supplied bytes and externally pinned evaluator attestations
satisfy this contract, not that this reducer independently reran every test.
No reference/test-key campaign or missing mandatory gate can authorize release.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import sqlite3

from .ontos_epoch_journal_core import Cursor
from .ontos_v72_quorum_journal import QuorumEpochJournal

from .ontos_v75_manifest import SourceArchive, verify_manifest
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_evidence import ArtifactBundle, verify_record
from .ontos_v72_receipts import ReceiptScope, _prime_order_point
from .ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign
from .ontos_v75_anchor import (AnchorTrust, AnchorEvidence, QuorumAnchorTrust, QuorumAnchorEvidence,
                               review_leaf, verify_review_anchor)

GATES = tuple(f'GATE-0{i}' for i in range(1,9))
_HEX = re.compile(r'[0-9a-f]{64}\Z',re.ASCII)


def _hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class JournalQuorumAnchorTrust:
    """Operator-selected durable quorum; retain the returned cursor independently."""
    journal: QuorumEpochJournal
    expected: Cursor
    challenge: bytes

    def __post_init__(self):
        if (type(self.journal) is not QuorumEpochJournal or type(self.expected) is not Cursor
                or type(self.challenge) is not bytes or len(self.challenge) != 32):
            raise ValueError('typed journal, retained cursor and challenge required')
        self.expected.__post_init__()


@dataclass(frozen=True, slots=True)
class GateEvidence:
    record: dict
    receipt: dict
    artifacts: ArtifactBundle


def gate_provenance(scope: ReceiptScope, manifest_pin: str, campaign_pin: str | None) -> bytes:
    if type(scope) is not ReceiptScope or scope.level_id!='L12' or not _hex(manifest_pin) or (campaign_pin is not None and not _hex(campaign_pin)):
        raise ValueError('invalid gate provenance scope')
    return canonical_json({'policy':'omega-v75-gate-v1','scope':scope.body(),
        'manifest_file_sha256':manifest_pin,'source_campaign_sha256':campaign_pin})


def _source_campaign(data, pin):
    if type(data) is not bytes or len(data)>1024*1024 or sha256(data).hexdigest()!=pin:
        return False
    try:
        obj = parse_json(data)
        if (type(obj) is not dict or set(obj)!={'schema','source_reproduction_verified',
                'test_keys_only','plan','plan_sha256','records','details','report'}
                or obj['schema']!='omega-v75-source-execution-v1'
                or obj['source_reproduction_verified'] is not True or obj['test_keys_only'] is not False
                or type(obj['records']) is not list or len(obj['records'])!=1800
                or type(obj['details']) is not list or len(obj['details'])!=1800):
            return False
        p = obj['plan']
        if (type(p) is not dict or set(p)!={'seeds','configurations','comparisons','analysis_seed','protocol_sha256'}
                or type(p['seeds']) is not list or type(p['configurations']) is not list
                or type(p['comparisons']) is not list or any(type(x) is not list for x in p['comparisons'])):
            return False
        plan = CampaignPlan(tuple(p['seeds']),tuple(Configuration(**c) for c in p['configurations']),
            tuple(tuple(x) for x in p['comparisons']),p['analysis_seed'],p['protocol_sha256'])
        if plan.digest()!=obj['plan_sha256']:
            return False
        configs = {c.name:c for c in plan.configurations}
        details = {}
        for row in obj['details']:
            if (type(row) is not dict or type(row.get('configuration')) is not str
                    or row['configuration'] not in configs or type(row.get('seed')) is not int
                    or row['seed'] not in plan.seeds or type(row.get('correct')) is not int
                    or row.get('suite')!=configs[row['configuration']].suite):
                return False
            key = (row['configuration'],row['seed'])
            if key in details:
                return False
            details[key] = row
        runs = []
        for row in obj['records']:
            run = Run(**row)
            detail = details.get((run.configuration,run.seed))
            if detail is None or detail['correct']!=run.correct or sha256(canonical_json(detail)).hexdigest()!=run.evidence_sha256:
                return False
            runs.append(run)
        recomputed = analyze_campaign(plan,obj['plan_sha256'],tuple(runs))
        # Arithmetic integrity is checked here; original source identity and
        # experimental truth still require pinned full-scope evaluator evidence.
        return recomputed['all_runs_recorded'] and canonical_json(recomputed)==canonical_json(obj['report'])
    except (ValueError,TypeError,KeyError,RecursionError,OverflowError):
        return False


def audit_l12(raw_manifest: bytes, manifest_pin: str, payloads: dict[str,bytes] | SourceArchive, *,
              commit_sha: str, tenant: str, source_campaign_sha256: str | None,
              trust: dict[str,tuple[ReceiptScope,bytes]],
              submissions: dict[str,GateEvidence],
              anchor_trust: AnchorTrust | QuorumAnchorTrust | JournalQuorumAnchorTrust | None = None,
              anchor_evidence: AnchorEvidence | QuorumAnchorEvidence | None = None) -> dict:
    """Use only externally pinned gate scopes and keys, never submitted trust roots.

    All eight gates are mandatory. A source campaign pin is required for 04/05;
    a reviewed source claim is attested by the trusted full-scope evaluators.
    The source campaign marker alone does not prove an experiment occurred.
    GATE-09 additionally requires the exact review at the fresh witness tip.
    Journal mode commits that review under CAS before returning PASS. The caller
    must retain the returned anchor_cursor in an independent trust domain.
    """
    ReceiptScope('L12','GATE-01',commit_sha,tenant,'policy')
    if (not _hex(manifest_pin) or source_campaign_sha256 is not None and not _hex(source_campaign_sha256)
            or type(trust) is not dict or type(submissions) is not dict
            or not set(trust)<=set(GATES) or not set(submissions)<=set(GATES)):
        raise ValueError('bounded pinned gate review required')
    for gate,pair in trust.items():
        if (type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not ReceiptScope
                or pair[0].level_id!='L12' or pair[0].gate_id!=gate or pair[0].commit_sha!=commit_sha
                or pair[0].tenant!=tenant or not _prime_order_point(pair[1])):
            raise ValueError('invalid trusted evaluator scope or key')
        pair[0].__post_init__()
    manifest = verify_manifest(raw_manifest,manifest_pin,payloads)
    results = {}
    authenticated_receipts = {}
    for gate in GATES:
        if gate in ('GATE-01','GATE-08') and manifest['status']=='FAIL':
            results[gate]='FAIL'; continue
        if gate not in submissions:
            results[gate]='BLOCKED'; continue
        item = submissions[gate]
        if gate not in trust or type(item) is not GateEvidence:
            results[gate]='FAIL'; continue
        scope,key = trust[gate]
        try:
            receipt = parse_json(canonical_json(item.receipt))
        except (ValueError,TypeError,RecursionError):
            results[gate]='FAIL'; continue
        check = verify_record(item.record,receipt,scope,key,item.artifacts)
        if not check['authenticated']:
            results[gate]='FAIL'; continue
        rec = item.record
        if (rec['identity']['package_id']!='L12-04/GATE' or rec['contract']['version']!='omega-v75-gate-v1'
                or rec['contract']['domain']!='L12-full' or rec['test']['test_id']!='L12/'+gate
                or item.artifacts.provenance!=gate_provenance(scope,manifest_pin,source_campaign_sha256)):
            results[gate]='FAIL'; continue
        status = check['record_status']
        if status!='PASS':
            results[gate]='FAIL' if status=='FAIL' else 'BLOCKED'; continue
        if gate in ('GATE-01','GATE-08') and manifest['status']!='PASS':
            results[gate]='BLOCKED'; continue
        if gate in ('GATE-04','GATE-05'):
            if source_campaign_sha256 is None:
                results[gate]='BLOCKED'; continue
            if not _source_campaign(item.artifacts.replay,source_campaign_sha256):
                results[gate]='FAIL'; continue
        if gate=='GATE-07' and not rec['fault_model']['crash_restart_tested']:
            results[gate]='FAIL'; continue
        authenticated_receipts[gate] = receipt
        results[gate]='PASS'
    final = 'FAIL' if 'FAIL' in results.values() else 'PASS' if all(x=='PASS' for x in results.values()) else 'BLOCKED'
    anchor_status = 'BLOCKED'
    anchor_cursor = None
    if final == 'PASS':
        if anchor_trust is not None and anchor_evidence is not None:
            try:
                leaf = review_leaf(commit_sha=commit_sha,tenant=tenant,manifest_pin=manifest_pin,
                                   campaign_pin=source_campaign_sha256,trust=trust,
                                   receipts=authenticated_receipts)
                keys = tuple(trust[gate][1] for gate in GATES)
                if type(anchor_trust) is JournalQuorumAnchorTrust:
                    anchor_trust.__post_init__()
                    if type(anchor_evidence) is not QuorumAnchorEvidence:
                        anchor_status = 'FAIL'
                    else:
                        update = anchor_trust.journal.commit_review(anchor_trust.expected, leaf,
                            anchor_evidence.certificate, anchor_evidence.inclusion, keys,
                            challenge=anchor_trust.challenge)
                        if update.status == 'COMMITTED':
                            cursor = update.snapshot.cursor
                            anchor_cursor = {'sequence': cursor.sequence, 'digest': cursor.digest.hex()}
                            anchor_status = 'PASS'
                        else:
                            anchor_status = 'FAIL' if update.status == 'REJECTED' else 'BLOCKED'
                else:
                    anchor_status = 'PASS' if verify_review_anchor(leaf,anchor_trust,anchor_evidence, keys) else 'FAIL'
            except (sqlite3.Error, OSError):
                anchor_status = 'BLOCKED'
            except (ValueError,TypeError,KeyError,RecursionError):
                anchor_status = 'FAIL'
        final = anchor_status
    results['GATE-09'] = final
    result = {'schema':'omega-v75-l12-review-v1','commit_sha':commit_sha,'tenant':tenant,
            'manifest':manifest,'gates':results,'source_campaign_sha256':source_campaign_sha256,
            'engineering_acceptance_status':final,'anchor_status':anchor_status,'release_authorized':False}
    if type(anchor_trust) is JournalQuorumAnchorTrust:
        result['anchor_cursor'] = anchor_cursor
    return result
