"""Canonical L12-L111 map: governance, full graph and package dependencies."""
from dataclasses import replace

import pytest

from omega_x_evolution.ultra_evolution_map import (
    LEVELS, EPOCHS, TRACKS, CROSS_DEPENDENCIES, INVARIANTS, GATES,
    CRITICAL_SECURITY_PATH, CrossDependency, get_level, generate_400_packages,
    validate_dag, evaluate_dependency_readiness,
)


def test_exact_canonical_map_counts_and_scope():
    result = validate_dag()
    assert result['status'] == 'PASS'
    assert result['levels'] == 100 and result['packages'] == 400
    assert result['binding_levels'] == 1 and result['proposed_levels'] == 99
    assert result['epochs'] == 10 and result['tracks'] == 8
    assert result['cross_dependencies'] == 16 and result['invariants'] == 12 and result['gates'] == 9
    assert result['cycles_found'] == 0 and result['topological_length'] == 100
    assert get_level('L12').governance_status == 'BINDING_ROADMAP'
    assert all(x.governance_status == 'PROPOSED_NON_BINDING' for x in LEVELS[1:])
    assert CRITICAL_SECURITY_PATH == ('L14','L18','L29','L43','L74','L106')
    assert result['release_authorized'] is False


def test_package_graph_all_edges_and_phase_order():
    packages = generate_400_packages()
    assert len({p.package_id for p in packages}) == 400
    assert sum(p.governance_status == 'BINDING_ROADMAP' for p in packages) == 4
    seen = set()
    for p in packages:
        assert set(p.dependencies) <= seen
        seen.add(p.package_id)
    index = {p.package_id:p for p in packages}
    assert index['L12-01/SPEC'].dependencies == ()
    assert index['L12-02/BUILD'].dependencies == ('L12-01/SPEC',)
    assert index['L12-03/TEST'].dependencies == ('L12-02/BUILD',)
    assert index['L12-04/GATE'].dependencies == ('L12-03/TEST',)
    assert 'L32-04/GATE' in index['L95-01/SPEC'].dependencies
    assert 'L94-04/GATE' in index['L95-01/SPEC'].dependencies


def test_transitive_cross_readiness_and_no_authority():
    all_pass = {x.level_id:'PASS' for x in LEVELS}
    assert evaluate_dependency_readiness('L111', all_pass)['ready']
    all_pass['L12'] = 'OPEN'
    r = evaluate_dependency_readiness('L111', all_pass)
    assert not r['ready'] and r['status'] == 'BLOCKED'
    assert 'L12' in {b['dependency'] for b in r['blocking_dependencies']}
    assert r['release_authorized'] is False
    r = evaluate_dependency_readiness('L95', {'L36':'PASS','L94':'PASS'})
    assert 'L32' in {b['dependency'] for b in r['blocking_dependencies']}


def test_cycle_detected_in_cross_edges_not_only_direct_edges():
    bad = CROSS_DEPENDENCIES[:-1] + (CrossDependency('L111','L12','cycle'),)
    with pytest.raises(ValueError, match='cycle'): validate_dag(cross_dependencies=bad)


@pytest.mark.parametrize('change', [
    {'dependencies':('L999',)}, {'dependencies':('L13',)},
    {'governance_status':'BINDING_ROADMAP'}, {'epoch_id':'E10'},
    {'dependencies':('L12','L12')},
])
def test_invalid_level_metadata_rejected(change):
    levels = LEVELS[:1] + (replace(LEVELS[1], **change),) + LEVELS[2:]
    with pytest.raises(ValueError): validate_dag(levels=levels)


def test_invalid_cross_edges_and_lookup():
    for edge in (CrossDependency('L999','L12','bad'), CrossDependency('L12','L12','self'), CROSS_DEPENDENCIES[0]):
        with pytest.raises(ValueError): validate_dag(cross_dependencies=CROSS_DEPENDENCIES[:-1]+(edge,))
    with pytest.raises(KeyError): get_level('L112')
    with pytest.raises(ValueError): evaluate_dependency_readiness('L12', {'L12':'BOGUS'})
