"""Diagnostic evidence must be real, reproducible, and truth-separated."""
import hashlib
import json
import pytest

from scripts.ontos_phase0_seed_diagnostics import (
    SEEDS, ACTIONS, observe_only, memory_attack_probe, report,
)
from omega_x_evolution.ontos_testbed import replay


def test_pinned_failure_seeds_and_full_trace_counts():
    assert SEEDS==(9216,9274,9651)
    r=report()
    assert len(r['rows'])==3
    for row in r['rows']:
        assert row['observation_count']==240 and row['scorer_count']==240
        assert row['floor_preserved']
        assert row['tamper_count']==12
        assert row['correct'] < 240
        assert len(row['trace_sha256'])==64
        assert 'true_state' not in row['observations_only'][0]
        assert 'posterior' not in row['scorer_only'][0]


def test_recorded_trace_hash_matches_actual_replay():
    from dataclasses import asdict
    for row in report()['rows']:
        steps=replay(row['seed'],ACTIONS)
        digest=hashlib.sha256(json.dumps([asdict(x) for x in steps],sort_keys=True,
                                  separators=(',',':'),allow_nan=False).encode()).hexdigest()
        assert digest==row['trace_sha256']


def test_seed_diagnostics_immutable_replay():
    r=report()
    assert json.dumps(r,sort_keys=True,allow_nan=False)==json.dumps(report(),sort_keys=True,allow_nan=False)


def test_poison_probe_not_automatically_promoted():
    for seed in SEEDS:
        row=memory_attack_probe(seed)
        assert row['pre_e_value']=='32'
        assert row['post_e_value']=='32/3'
        assert row['pre_eligible_for_manual_review']
        assert not row['post_eligible_for_manual_review']
        assert not row['automatic_promotion']


def test_unsupported_seed_rejected():
    with pytest.raises(ValueError): memory_attack_probe(1)


def test_observer_cannot_read_evaluator_truth():
    from omega_x_evolution.ontos_testbed import Observation
    v=(Observation(0,1,(0.,)*6,0.,False,False),)
    out=observe_only(v)
    assert len(out)==1
    assert out[0]['posterior'][1]>out[0]['posterior'][0]
    assert 'ood' not in out[0]
    assert 'correct' not in out[0]
