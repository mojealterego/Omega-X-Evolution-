"""L12 v72 Section 10 evidence schema and authenticated artifact binding.

Authenticates declared evidence and actual bytes; cannot prove that a log is
truthful or authorize promotion. The evaluator/key custody is external.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import math
import re
from typing import Any

from .ontos_v72_jcs import canonical_json
from .ontos_v72_receipts import ReceiptScope, verify_receipt

_MAX_ARTIFACT = 16 * 1024 * 1024
_HEX40 = re.compile(r'[0-9a-f]{40}\Z', re.ASCII)
_HEX64 = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_PACKAGE = re.compile(r'L(?:1[1-9]|[2-9][0-9]|10[0-9]|11[01])-(?:01/SPEC|02/BUILD|03/TEST|04/GATE)\Z', re.ASCII)
_TIMESTAMP = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z\Z', re.ASCII)
_MODES = frozenset({'NATIVE', 'DETERMINISTIC-SIMULATION', 'HYBRID', 'DEPLOYED'})
_DECISIONS = frozenset({'PASS', 'FAIL', 'BLOCKED', 'UNKNOWN', 'NOT_APPLICABLE'})


def _require(condition: bool, field: str) -> None:
    if not condition:
        raise ValueError('invalid evidence field: ' + field)


def _obj(value: Any, fields: str, name: str) -> dict:
    _require(type(value) is dict and set(value) == set(fields.split()), name)
    return value


def _text(value: Any) -> bool:
    return type(value) is str and bool(value.strip())


def _texts(value: Any) -> bool:
    return type(value) is list and all(type(item) is str for item in value)


def _match(value: Any, pattern: re.Pattern) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def _nullable_text(value: Any) -> bool:
    return value is None or _text(value)


def _number(value: Any, upper: float = math.inf) -> bool:
    return value is None or (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= upper)


def validate_record(record: Any) -> None:
    """Reject missing/extra fields and invalid Section 10 semantic combinations."""
    canonical_json(record)  # bound traversal, reject malformed JSON types/numbers
    r = _obj(record, 'identity contract environment test verification fault_model metrics decision promotion', 'record')
    i = _obj(r['identity'], 'package_id commit_sha source_sha256 timestamp_utc', 'identity')
    _require(_match(i['package_id'], _PACKAGE), 'identity.package_id')
    _require(_match(i['commit_sha'], _HEX40), 'identity.commit_sha')
    _require(_match(i['source_sha256'], _HEX64), 'identity.source_sha256')
    _require(_match(i['timestamp_utc'], _TIMESTAMP), 'identity.timestamp_utc')
    datetime.fromisoformat(i['timestamp_utc'].replace('Z', '+00:00'))
    c = _obj(r['contract'], 'version assumptions preconditions domain rights tenant', 'contract')
    for k in ('version', 'domain', 'tenant'):
        _require(_text(c[k]), 'contract.' + k)
    for k in ('assumptions', 'preconditions', 'rights'):
        _require(_texts(c[k]), 'contract.' + k)
    e = _obj(r['environment'], 'os hardware compiler_or_runtime solver pinned_dependencies', 'environment')
    for k in ('os', 'hardware', 'compiler_or_runtime'):
        _require(_text(e[k]), 'environment.' + k)
    _require(_nullable_text(e['solver']), 'environment.solver')
    deps = e['pinned_dependencies']
    _require(type(deps) is dict and all(_text(k) and _text(v) for k,v in deps.items()), 'environment.pinned_dependencies')
    t = _obj(r['test'], 'test_id seed command start_state exit_code log_sha256', 'test')
    for k in ('test_id', 'command', 'start_state'):
        _require(_text(t[k]), 'test.' + k)
    _require(type(t['seed']) is int or _text(t['seed']), 'test.seed')
    _require(type(t['exit_code']) is int, 'test.exit_code')
    _require(_match(t['log_sha256'], _HEX64), 'test.log_sha256')
    v = _obj(r['verification'], 'mode model_limitations', 'verification')
    _require(type(v['mode']) is str and v['mode'] in _MODES, 'verification.mode')
    limits = v['model_limitations']
    _require(_texts(limits), 'verification.model_limitations')
    if v['mode'] in ('DETERMINISTIC-SIMULATION', 'HYBRID'):
        _require(bool(limits) and all(_text(x) for x in limits), 'verification.simulation_limitations')
    f = _obj(r['fault_model'], 'injection_schedule retries crash_restart_tested replay_artifact_sha256', 'fault_model')
    _require(_texts(f['injection_schedule']), 'fault_model.injection_schedule')
    _require(type(f['retries']) is int and f['retries'] >= 0, 'fault_model.retries')
    _require(type(f['crash_restart_tested']) is bool, 'fault_model.crash_restart_tested')
    replay = f['replay_artifact_sha256']
    _require(replay is None or _match(replay, _HEX64), 'fault_model.replay_artifact_sha256')
    _require(not f['crash_restart_tested'] or replay is not None, 'fault_model.restart_requires_replay')
    m = _obj(r['metrics'], 'correctness latency_p95_ms latency_p99_ms memory_mib energy_joules provenance_sha256', 'metrics')
    _require(_number(m['correctness'], 1), 'metrics.correctness')
    for k in ('latency_p95_ms', 'latency_p99_ms', 'memory_mib', 'energy_joules'):
        _require(_number(m[k]), 'metrics.' + k)
    a, b = m['latency_p95_ms'], m['latency_p99_ms']
    _require(a is None or b is None or a <= b, 'metrics.percentile_order')
    _require(_match(m['provenance_sha256'], _HEX64), 'metrics.provenance_sha256')
    d = _obj(r['decision'], 'status reason', 'decision')
    _require(type(d['status']) is str and d['status'] in _DECISIONS, 'decision.status')
    _require(_text(d['reason']), 'decision.reason')
    p = _obj(r['promotion'], 'operator_approval_required operator_approval_id rollback_ref regression_ref', 'promotion')
    _require(type(p['operator_approval_required']) is bool, 'promotion.operator_approval_required')
    _require(_nullable_text(p['operator_approval_id']), 'promotion.operator_approval_id')
    _require(_text(p['rollback_ref']), 'promotion.rollback_ref')
    _require(_nullable_text(p['regression_ref']), 'promotion.regression_ref')
    if d['status'] == 'PASS':
        _require(t['exit_code'] == 0, 'decision.pass_requires_zero_exit')
        _require(v['mode'] != 'DEPLOYED', 'decision.deployment_is_not_verification')
        _require(not p['operator_approval_required'] or _text(p['operator_approval_id']), 'promotion.approval_reference_required')


@dataclass(frozen=True, slots=True)
class ArtifactBundle:
    source: bytes
    log: bytes
    provenance: bytes
    replay: bytes | None = None

    def __post_init__(self) -> None:
        for data in (self.source, self.log, self.provenance):
            _require(type(data) is bytes and 0 < len(data) <= _MAX_ARTIFACT, 'artifact.byte_budget')
        _require(self.replay is None or (type(self.replay) is bytes and 0 < len(self.replay) <= _MAX_ARTIFACT), 'artifact.replay_budget')


def _digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def verify_record(record: Any, receipt: Any, expected_scope: ReceiptScope,
                  trusted_public_key: bytes, artifacts: ArtifactBundle) -> dict:
    """Bind nine-section schema, trusted scope, signature and supplied artifact bytes."""
    result = {'authenticated': False, 'record_status': None, 'release_authorized': False}
    try:
        validate_record(record)
        _require(type(expected_scope) is ReceiptScope and type(artifacts) is ArtifactBundle, 'typed_verifier_inputs')
        expected_scope.__post_init__()
        artifacts.__post_init__()
        i = record['identity']
        _require(i['package_id'].split('-')[0] == expected_scope.level_id and i['commit_sha'] == expected_scope.commit_sha and record['contract']['tenant'] == expected_scope.tenant, 'receipt.scope_binding')
        _require(i['source_sha256'] == _digest(artifacts.source), 'artifact.source_digest')
        _require(record['test']['log_sha256'] == _digest(artifacts.log), 'artifact.log_digest')
        _require(record['metrics']['provenance_sha256'] == _digest(artifacts.provenance), 'artifact.provenance_digest')
        _require(record['fault_model']['replay_artifact_sha256'] == _digest(artifacts.replay), 'artifact.replay_digest')
        _require(verify_receipt(receipt, record, expected_scope, trusted_public_key), 'receipt.signature')
        return {**result, 'authenticated': True, 'record_status': record['decision']['status']}
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return result
