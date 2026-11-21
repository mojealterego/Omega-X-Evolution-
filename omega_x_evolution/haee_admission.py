"""HAEE v1.0.0 optional research admission: schema subset plus graph semantics.

Does NOT compile a neural graph, evaluate a candidate, allocate infrastructure,
change fitness, or issue promotion rights. Source is a specification, not a
runtime implementation. No untrusted expression is ever executed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import heapq
import json
import math
import re
import uuid
from typing import Any

NODE_KINDS = frozenset(('INPUT','OUTPUT','LINEAR','ATTENTION','RECURRENT','FFN'))
ACTIVATIONS = frozenset(('NONE','RELU','GELU','TANH','SILU'))
OPERATORS = frozenset(('BASELINE','MUTATE_PARAM','ADD_NODE','REMOVE_NODE','ADD_EDGE',
                       'REMOVE_EDGE','FUSE_SUBGRAPH','SWITCH_OPTIMIZER','MUTATE_LOSS',
                       'MUTATE_SCHEDULE','SHOCK_MUTATION'))
OBJECTIVES = frozenset(('TASK_ERROR','GPU_SECONDS','ROBUSTNESS_DROP','PARAMETER_COUNT',
                        'ENERGY_JOULES','PEAK_MEMORY_MIB'))
PROFILES = frozenset(('OFFLINE_ANDROID_ARM64','DESKTOP_LOCAL','HYBRID','CLOUD_HPC'))
_NODE_ID = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,63}\Z')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _keys(obj: object, keys: set[str]) -> dict[str, Any]:
    if type(obj) is not dict or set(obj) != keys:
        raise ValueError('invalid or unexpected schema keys')
    return obj


def _text(value: object, max_len: int = 128) -> bool:
    return type(value) is str and 0 < len(value) <= max_len and all(c.isprintable() for c in value)


def _integer(value: object, lo: int, hi: int) -> bool:
    return type(value) is int and lo <= value <= hi


def _number(value: object, lo: float, hi: float, *, positive: bool = False) -> bool:
    return (type(value) in (int, float) and lo <= value <= hi and
            (not positive or value > lo) and math.isfinite(value))


def _uuid(value: object) -> bool:
    if not _text(value, 64):
        return False
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    """Independent testbed limits, not the source manifest's declared budgets."""

    max_nodes: int = 128
    max_edges: int = 512
    max_tensor_elements: int = 2_000_000
    max_evaluations: int = 10_000
    max_parallel: int = 64
    max_wall_clock_minutes: int = 1_440
    max_memory_mib: int = 16_384

    def __post_init__(self) -> None:
        if any(not _integer(value, 1, 100_000_000) for value in (
                self.max_nodes, self.max_edges, self.max_tensor_elements,
                self.max_evaluations, self.max_parallel, self.max_wall_clock_minutes,
                self.max_memory_mib)):
            raise ValueError('invalid admission bounds')


@dataclass(frozen=True, slots=True)
class AdmissionRecord:
    sha256: str
    ordered_nodes: tuple[str, ...]
    delayed_edges: int
    activation_elements_upper: int
    can_execute: bool = False
    can_promote: bool = False
    shape_compatibility_verified: bool = False


def _validate_genome(g: dict, p: AdmissionPolicy) -> tuple[tuple[str, ...], int, int]:
    _keys(g, {'schema_version','genome_id','task_id','seed','nodes','edges',
              'training','limits','lineage'})
    if g['schema_version'] != '1.0.0' or not _uuid(g['genome_id']) or not _text(g['task_id']):
        raise ValueError('genome identity')
    if not _integer(g['seed'], 0, 2**64-1):
        raise ValueError('genome seed')
    nodes = g['nodes']
    edges = g['edges']
    if (type(nodes) is not list or not 2 <= len(nodes) <= min(4096, p.max_nodes)
            or type(edges) is not list or len(edges) > min(16384,p.max_edges)):
        raise ValueError('graph cardinality')
    ids: dict[str,str] = {}
    elements = 0
    inputs: list[str] = []
    outputs: list[str] = []
    for node in nodes:
        _keys(node, {'id','kind','shape','activation'})
        name, kind, shape = node['id'], node['kind'], node['shape']
        if type(name) is not str or not _NODE_ID.fullmatch(name) or name in ids:
            raise ValueError('duplicate or invalid node id')
        if type(kind) is not str or kind not in NODE_KINDS or type(node['activation']) is not str or node['activation'] not in ACTIVATIONS:
            raise ValueError('invalid node type/activation')
        if type(shape) is not list or not 2 <= len(shape) <= 6:
            raise ValueError('invalid node rank')
        size = 1
        for dim in shape:
            if not _integer(dim, 1, p.max_tensor_elements):
                raise ValueError('invalid dimension')
            size *= dim
            if size > p.max_tensor_elements:
                raise ValueError('tensor bound')
        elements += size
        if elements > p.max_tensor_elements:
            raise ValueError('total tensor bound')
        ids[name] = kind
        if kind == 'INPUT':
            inputs.append(name)
        if kind == 'OUTPUT':
            outputs.append(name)
    if not inputs or not outputs:
        raise ValueError('missing inputs or outputs')
    adjacency: dict[str, set[str]] = {name: set() for name in ids}
    all_adjacency: dict[str, set[str]] = {name: set() for name in ids}
    indegree = dict.fromkeys(ids, 0)
    seen_edges: set[tuple[str,str,int]] = set()
    delayed = 0
    for edge in edges:
        _keys(edge, {'source','target','delay_steps'})
        source,target,delay = edge['source'],edge['target'],edge['delay_steps']
        if type(source) is not str or type(target) is not str or source not in ids or target not in ids:
            raise ValueError('dangling edge')
        if not _integer(delay, 0, 1024):
            raise ValueError('invalid edge delay')
        key = (source,target,delay)
        if key in seen_edges:
            raise ValueError('duplicate edge')
        seen_edges.add(key)
        all_adjacency[source].add(target)
        if delay == 0:
            adjacency[source].add(target)
            indegree[target] += 1
        else:
            delayed += 1
    heap = [name for name,v in indegree.items() if v == 0]
    heapq.heapify(heap)
    order = []
    while heap:
        name=heapq.heappop(heap)
        order.append(name)
        for child in sorted(adjacency[name]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(heap,child)
    if len(order) != len(nodes):
        raise ValueError('zero-delay cycle')
    reachable = set(inputs)
    pending=list(inputs)
    while pending:
        current=pending.pop()
        for child in all_adjacency[current]-reachable:
            reachable.add(child)
            pending.append(child)
    if any(output not in reachable for output in outputs):
        raise ValueError('unreachable output')
    training = _keys(g['training'],{'optimizer','learning_rate','weight_decay','loss_id','epochs','batch_size'})
    if (type(training['optimizer']) is not str or training['optimizer'] not in ('SGD','ADAMW') or
        type(training['loss_id']) is not str or training['loss_id'] not in ('CROSS_ENTROPY','MSE','MAE') or
        not _number(training['learning_rate'],0,1,positive=True) or
        not _number(training['weight_decay'],0,1) or
        not _integer(training['epochs'],1,2000) or
        not _integer(training['batch_size'],1,4096)):
        raise ValueError('training contract')
    limits = _keys(g['limits'],{'max_nodes','max_edges','max_train_seconds','max_memory_mib'})
    if (any(not _integer(limits[field],1,2**32-1) for field in limits)
            or len(nodes)>limits['max_nodes'] or len(edges)>limits['max_edges'] or
            limits['max_memory_mib']>p.max_memory_mib or
            (elements*4 > limits['max_memory_mib']*1024*1024)):
        raise ValueError('resource budget or activation lower bound')
    lineage=_keys(g['lineage'],{'parent_ids','operator','mutation_seed'})
    if (type(lineage['operator']) is not str or lineage['operator'] not in OPERATORS or
        not _integer(lineage['mutation_seed'],0,2**64-1) or
        type(lineage['parent_ids']) is not list or len(lineage['parent_ids'])>4 or
        any(not _text(s) for s in lineage['parent_ids']) or
        len(set(lineage['parent_ids']))!=len(lineage['parent_ids'])):
        raise ValueError('lineage')
    return tuple(order),delayed,elements


def _validate_experiment(e: dict, p: AdmissionPolicy) -> None:
    _keys(e, {'schema_version','experiment_id','tenant_id','task_id','dataset','baseline_candidate_id',
              'seed','population','max_generations','max_evaluations','max_wall_clock_minutes',
              'max_parallel_evaluations','run_profile','objective_ids','allowed_operators',
              'approval_policy','allow_external_dataset_egress'})
    if (e['schema_version']!='1.0.0' or not _uuid(e['experiment_id']) or
        any(not _text(e[key]) for key in ('tenant_id','task_id','baseline_candidate_id')) or
        not _integer(e['seed'],0,2**64-1)):
        raise ValueError('experiment identifiers')
    dataset=_keys(e['dataset'],{'train_sha256','validation_sha256'})
    if any(type(v) is not str or not _SHA.fullmatch(v) for v in dataset.values()):
        raise ValueError('dataset integrity digests')
    if (not _integer(e['population'],2,100_000) or not _integer(e['max_generations'],1,1_000_000) or
        not _integer(e['max_evaluations'],1,p.max_evaluations) or
        not _integer(e['max_wall_clock_minutes'],1,p.max_wall_clock_minutes) or
        not _integer(e['max_parallel_evaluations'],1,p.max_parallel) or
        e['max_parallel_evaluations']>e['max_evaluations'] or
        type(e['run_profile']) is not str or e['run_profile'] not in PROFILES):
        raise ValueError('experiment quotas')
    objectives=e['objective_ids']
    operators=e['allowed_operators']
    if (type(objectives) is not list or not 2<=len(objectives)<=len(OBJECTIVES) or
        any(type(v) is not str or v not in OBJECTIVES for v in objectives) or
        len(set(objectives))!=len(objectives) or
        type(operators) is not list or not 1<=len(operators)<=len(OPERATORS)-1 or
        any(type(v) is not str or v not in OPERATORS-{'BASELINE'} for v in operators) or
        len(set(operators))!=len(operators)):
        raise ValueError('objectives or mutation allowlist')
    if (e['approval_policy']!='HUMAN_BEFORE_PROMOTION' or
        e['allow_external_dataset_egress'] is not False):
        raise ValueError('research admission cannot authorize promotion or egress')


def admit_haee(genome: dict, experiment: dict, policy: AdmissionPolicy = AdmissionPolicy()) -> AdmissionRecord:
    """Admit source v1 manifests for *offline research only*, without execution.

    v1 lacks port, dtype and weight-binding semantics; shape compatibility and
    real neural compilation must remain UNVERIFIED even on successful admission.
    """
    if type(policy) is not AdmissionPolicy:
        raise ValueError('invalid admission policy')
    policy.__post_init__()
    if type(genome) is not dict or type(experiment) is not dict:
        raise ValueError('must supply two manifest objects')
    ordered,delayed,elements = _validate_genome(genome,policy)
    _validate_experiment(experiment,policy)
    if genome['task_id']!=experiment['task_id']:
        raise ValueError('cross-manifest task mismatch')
    operator = genome['lineage']['operator']
    if operator!='BASELINE' and operator not in experiment['allowed_operators']:
        raise ValueError('mutation operator forbidden by experiment')
    try:
        normalized = dict(genome)
        normalized['nodes']=sorted(genome['nodes'],key=lambda n:n['id'])
        normalized['edges']=sorted(genome['edges'],key=lambda n:(n['source'],n['target'],n['delay_steps']))
        payload=json.dumps({'genome':normalized,'experiment':experiment,'admission_policy':asdict(policy)},ensure_ascii=False,
                           sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    except (TypeError,OverflowError,RecursionError,UnicodeError) as exc:
        raise ValueError('invalid canonical manifest') from exc
    if len(payload)>2_000_000:
        raise ValueError('manifest size cap')
    return AdmissionRecord(hashlib.sha256(payload).hexdigest(),ordered,delayed,elements)
