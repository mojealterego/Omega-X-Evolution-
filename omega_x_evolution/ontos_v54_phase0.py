"""Frozen Phase0 A/B reference replay with scorer separated from observer use.

This compares predetermined action tapes. It does not train, choose actions,
exercise native JEPA/HOPE, or establish production safety/accuracy. Ground
truth appears only in post-hoc scoring. Any unmetered work fails release gate.
"""
from __future__ import annotations
from dataclasses import asdict
from types import MappingProxyType
import hashlib
import json

from .ontos_testbed import replay
from .ontos_v50_belief import BeliefFilter
from .ontos_v52_temporal import TemporalEvent, temporal_view
from .ontos_v53_accounting import WorkLedger, WorkEstimate, estimate_kernel

PHASE0_SEEDS = tuple(9100 + 29*i for i in range(30))
TAPES = MappingProxyType({
    'A_cycle': (0,1,2,3)*60,
    'B_offset': (1,2,3,0)*60,
})
_TICK_COUNT=240
_SOURCE_OBSERVATION_SHA=hashlib.sha256(b'ontos-phase0-fixed-observation-reference-v1').hexdigest()


def _summarize(rows: list[dict]) -> dict:
    total=sum(x['steps'] for x in rows)
    accepted=total-sum(x['abstentions'] for x in rows)
    correct=sum(x['correct'] for x in rows)
    return {
        'steps':total, 'correct':correct, 'abstentions':total-accepted,
        'failures':total-correct,'harm':sum(x['harm'] for x in rows),
        'ood':sum(x['ood'] for x in rows),
        'lure_hits':sum(x['lure_hits'] for x in rows),
        'coverage':accepted/total if total else 0,
        'unconditional_accuracy':correct/total if total else None,
        'conditional_accuracy':correct/accepted if accepted else None,
        'target_reached':bool(rows) and correct/total >= .91 and sum(x['lure_hits'] for x in rows)==0,
    }


def _observe(rows: tuple) -> dict:
    """Only reads row.observation; never accesses row.true_state/regime/ood."""
    filter_=BeliefFilter()
    prior=(.25,.25,.25,.25)
    min_belief=1.
    events=[]
    observed=[]
    snapshots=0
    for i,scored in enumerate(rows):
        o=scored.observation
        likelihood=tuple(.9 if j==o.discrete else .1 for j in range(4))
        posterior=filter_.update(prior,likelihood)
        prior=posterior.posterior
        min_belief=min(min_belief,*prior)
        observed.append((o.step,o.discrete,prior,posterior.abstain))
        if i%60==0:
            e=TemporalEvent('Phase0',f'epoch-{i}',f'epoch-{i}',str(o.discrete),
                            _SOURCE_OBSERVATION_SHA,i,i+60,i,6)
            events.append(e)
            snap=temporal_view(tuple(events),tenant='Phase0',valid_at=i,known_at=i)
            if snap.visible != (e,):
                raise RuntimeError('temporal observation mismatch')
            snapshots+=1
    canonical=json.dumps(observed,ensure_ascii=True,allow_nan=False,
                         separators=(',',':')).encode('ascii')
    return {'belief_updates':len(observed),'temporal_snapshots':snapshots,
            'min_belief':min_belief,'trace_sha256':hashlib.sha256(canonical).hexdigest(),
            'ground_truth_access':False,'provenance_authenticated':False}


def run_phase0(seeds: tuple[int,...] = PHASE0_SEEDS) -> dict:
    """Precommitted 30 seeds and two fixed tapes; subset for focused tests.

    Reservation happens before replay. Observed op and I/O counts are UNKNOWN:
    the nominal reservation is an explicit model, not a physical measurement.
    """
    if (type(seeds) is not tuple or not 1 <= len(seeds) <= 30
        or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
        or len(set(seeds)) != len(seeds)):
        raise ValueError('bounded unique seed contract')
    per_seed=[]
    unmetered=0
    unit=estimate_kernel('inference',rows=4,cols=6)
    for seed in seeds:
        by_suite={}
        observer_results=[]
        for name,tape in TAPES.items():
            # Bound before calling the same real source-replay implementation
            # as v37/v48. This models reservation, not source instrumentation.
            ledger=WorkLedger(20000,100000).reserve('offline_replay',
                WorkEstimate('inference',unit.compute_units*_TICK_COUNT,
                             unit.io_bytes*_TICK_COUNT))
            result=replay(seed,tape)
            observer_results.append(_observe(result))
            ledger=ledger.settle('offline_replay',actual_compute_units=None,
                                 actual_io_bytes=None)
            if not ledger.complete:
                unmetered+=1
            raw=json.dumps([asdict(x) for x in result],sort_keys=True,
                           separators=(',',':'),allow_nan=False).encode('utf-8')
            correct=sum(x.correct for x in result)
            by_suite[name]={
                'steps':len(result),'correct':correct,
                'abstentions':sum(x.action==5 for x in result),
                'failures':len(result)-correct,
                'harm':sum(x.harm for x in result),
                'ood':sum(x.ood for x in result),
                'lure_hits':sum(x.observation.lure and x.action==4 for x in result),
                'trace_sha256':hashlib.sha256(raw).hexdigest(),
                'accounting':ledger.report(),
            }
        blob=json.dumps(observer_results,sort_keys=True,separators=(',',':'),
                        allow_nan=False).encode('ascii')
        per_seed.append({'seed':seed, 'per_suite':by_suite,
                         'scorer_truth_not_in_policy':True,
                         'observer':{'belief_updates':sum(x['belief_updates'] for x in observer_results),
                                     'temporal_snapshots':sum(x['temporal_snapshots'] for x in observer_results),
                                     'min_belief':min(x['min_belief'] for x in observer_results),
                                     'trace_sha256':hashlib.sha256(blob).hexdigest()}})
    suites={name:_summarize([x['per_suite'][name] for x in per_seed]) for name in TAPES}
    dev=per_seed[:20]
    held=per_seed[20:]
    return {
        'schema':'ontos-phase0-frozen-a-b-v1', 'policies':tuple(TAPES),
        'frozen_tapes':True,'operator_actions_enabled':False,
        'number_of_seeds':len(seeds),'total_steps':len(seeds)*2*_TICK_COUNT,
        'dev':{'seed_count':len(dev), 'suites':{name:_summarize([x['per_suite'][name] for x in dev]) for name in TAPES}},
        'independent_holdout':{'seed_count':len(held),
                               'suites':{name:_summarize([x['per_suite'][name] for x in held]) for name in TAPES}},
        'suites':suites,
        'target_lure_hits':0,
        'unmetered_operation_count':unmetered,
        'meets_source_target':len(seeds)==30 and all(s['target_reached'] for s in suites.values()) and unmetered==0,
        'eligible_for_release':False,
        'per_seed':per_seed,
    }
