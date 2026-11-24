"""L12 full-scope evidence admission and fail-closed gate reduction.

A PASS means the supplied bytes and externally pinned evaluator attestations
satisfy this contract, not that this reducer independently reran every test.
No reference/test-key campaign or missing mandatory gate can authorize release.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from .ontos_v49_manifest import SourceRecord, audit_inventory
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_evidence import ArtifactBundle, verify_record
from .ontos_v72_receipts import ReceiptScope, _prime_order_point
from .ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign

GATES = tuple(f'GATE-0{i}' for i in range(1,9))
_HEX = re.compile(r'[0-9a-f]{64}\Z',re.ASCII)


def _hex(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def verify_manifest(raw: bytes, pin: str, payloads: dict[str,bytes]) -> dict:
    """Verify exact registered inventory, byte digests and conservative reuse policy."""
    failed = {'status':'FAIL','inventory_verified':False,'registered':0,'checked_blobs':0,
              'release_authorized':False}
    try:
        if type(raw) is not bytes or len(raw)>1024*1024 or not _hex(pin) or sha256(raw).hexdigest()!=pin:
            return failed
        obj = parse_json(raw)
        if type(obj) is not dict or obj.get('schema')!='ontos-source-register-v49-v1' or type(obj.get('entries')) is not list or len(obj['entries'])!=33:
            return failed
        result = audit_inventory(tuple(SourceRecord(**row) for row in obj['entries']),payloads)
        if result['manifest_sha256']!=obj.get('entry_digest_sha256'):
            return failed
        return {**result,'status':'PASS' if result['eligible_for_manual_review'] else 'BLOCKED',
                'inventory_verified':True,'register_file_sha256':pin,'release_authorized':False}
    except (ValueError,TypeError,KeyError,RecursionError):
        return failed


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


def audit_l12(raw_manifest: bytes, manifest_pin: str, payloads: dict[str,bytes], *,
              commit_sha: str, tenant: str, source_campaign_sha256: str | None,
              trust: dict[str,tuple[ReceiptScope,bytes]],
              submissions: dict[str,GateEvidence]) -> dict:
    """Use only externally pinned gate scopes and keys, never submitted trust roots.

    All eight gates are mandatory. A source campaign pin is required for 04/05;
    a reviewed source claim is attested by the trusted full-scope evaluators.
    The source campaign marker alone does not prove an experiment occurred.
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
    for gate in GATES:
        if gate in ('GATE-01','GATE-08') and manifest['status']=='FAIL':
            results[gate]='FAIL'; continue
        if gate not in submissions:
            results[gate]='BLOCKED'; continue
        item = submissions[gate]
        if gate not in trust or type(item) is not GateEvidence:
            results[gate]='FAIL'; continue
        scope,key = trust[gate]
        check = verify_record(item.record,item.receipt,scope,key,item.artifacts)
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
        results[gate]='PASS'
    final = 'FAIL' if 'FAIL' in results.values() else 'PASS' if all(x=='PASS' for x in results.values()) else 'BLOCKED'
    results['GATE-09'] = final
    return {'schema':'omega-v75-l12-review-v1','commit_sha':commit_sha,'tenant':tenant,
            'manifest':manifest,'gates':results,'source_campaign_sha256':source_campaign_sha256,
            'engineering_acceptance_status':final,'release_authorized':False}
