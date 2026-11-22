"""OMEGA-CONST-001..013: finite, externally anchored preference checks.

No test asserts a proof of CEV, source attestation, reward hacking immunity,
or automatic authorization.
"""
import dataclasses
import hashlib
import json
import random

import pytest

from omega_x_evolution.polyglot import Program
from omega_x_evolution.rsi_ir_guard import Policy
from omega_x_evolution.constitutional_drift import (
    ConstitutionalCase, ConstitutionalSpec, assess_drift, review_rsi_with_drift,
)


def spec():
    return ConstitutionalSpec((
        ConstitutionalCase('critical_1', ('deny', 'allow'), 'deny', protected=True),
        ConstitutionalCase('critical_2', ('refuse', 'answer'), 'refuse', protected=True),
        ConstitutionalCase('style', ('concise', 'detailed'), 'concise'),
        ConstitutionalCase('format', ('json', 'markdown'), 'json'),
    ), max_noncritical_changes=1)


def baseline():
    return {'critical_1': 'deny', 'critical_2': 'refuse', 'style': 'concise', 'format': 'json'}


def test_const_001_stable_digest_and_exact_match():
    c = spec()
    assert c.digest == spec().digest
    r = assess_drift(c, baseline(), trusted_spec_digest=c.digest)
    assert r['status'] == 'PASS_FINITE_PROBE_UNATTESTED'
    assert r['deviations'] == 0
    assert r['protected_violations'] == 0
    assert r['observations_attested'] is False
    assert r['release_authorized'] is False
    assert r['human_values_alignment_proved'] is False


def test_const_002_bounded_noncritical_drift():
    c=spec(); a=baseline(); a['style']='detailed'
    r=assess_drift(c,a,trusted_spec_digest=c.digest)
    assert r['status']=='PASS_FINITE_PROBE_UNATTESTED'
    assert r['deviations']==1
    assert r['fraction_changed']==pytest.approx(0.25)
    a['format']='markdown'
    assert assess_drift(c,a,trusted_spec_digest=c.digest)['status']=='REJECT'


@pytest.mark.parametrize('which,action', [('critical_1', 'allow'), ('critical_2', 'answer')])
def test_const_003_protected_violations_always_reject(which,action):
    c=spec(); a=baseline(); a[which]=action
    out=assess_drift(c,a,trusted_spec_digest=c.digest)
    assert out['status']=='REJECT'
    assert out['protected_violations']==1


@pytest.mark.parametrize('bad', [
    {'critical_1': 'deny'},
    {'critical_1': 'deny', 'critical_2': 'refuse', 'style': 'concise', 'format': 'json', 'extra': 'json'},
    {'critical_1': 'deny', 'critical_2': 'refuse', 'style': 'UNLISTED', 'format': 'json'},
    {'critical_1': 'deny', 'critical_2': 'refuse', 'style': True, 'format': 'json'},
    ['deny','refuse','concise','json'],
])
def test_const_004_missing_extra_malformed_observations_fail_closed(bad):
    c=spec()
    assert assess_drift(c,bad,trusted_spec_digest=c.digest)['status']=='REJECT'


def test_const_005_external_anchor_mismatch_fails_closed():
    c=spec()
    with pytest.raises(ValueError):assess_drift(c,baseline(),trusted_spec_digest='0'*64)
    with pytest.raises(ValueError):assess_drift(c,baseline(),trusted_spec_digest='A'*64)
    with pytest.raises(ValueError):assess_drift(c,baseline(),trusted_spec_digest='')


def test_const_006_mutation_of_frozen_spec_detected_by_validation():
    c=spec()
    original_anchor = c.digest
    object.__setattr__(c.cases[0], 'expected', 'allow')
    with pytest.raises(ValueError):assess_drift(c,baseline(),trusted_spec_digest=original_anchor)


def test_const_007_external_anchor_detects_valid_but_changed_rules():
    c=spec(); approved=c.digest
    other=ConstitutionalSpec(c.cases, max_noncritical_changes=2)
    with pytest.raises(ValueError):assess_drift(other,baseline(),trusted_spec_digest=approved)


def test_const_008_reject_invalid_grammar_and_unsafe_spec():
    with pytest.raises(ValueError):ConstitutionalCase('bad space', ('deny','allow'),'deny')
    with pytest.raises(ValueError):ConstitutionalCase('id', ('deny','allow'),'unknown')
    with pytest.raises(ValueError):ConstitutionalCase('id', ('deny','deny'),'deny')
    with pytest.raises(ValueError):ConstitutionalCase('id', ('deny','allow'),'deny', protected=1)
    with pytest.raises(ValueError):ConstitutionalSpec((ConstitutionalCase('id', ('x','y'),'x'),)*2)
    with pytest.raises(ValueError):ConstitutionalSpec((ConstitutionalCase('id', ('x','y'),'x'),), max_noncritical_changes=2)
    with pytest.raises(ValueError):ConstitutionalSpec((ConstitutionalCase('id', ('x','y'),'x'),), max_noncritical_changes=True)


def test_const_009_no_protected_mutation_even_under_max_tolerance():
    c=ConstitutionalSpec((ConstitutionalCase('safety',('deny','allow'),'deny',protected=True),ConstitutionalCase('style',('x','y'),'x')),max_noncritical_changes=1)
    a={'safety':'allow','style':'x'}
    assert assess_drift(c,a,trusted_spec_digest=c.digest)['status']=='REJECT'


def test_const_010_finite_large_scale_128_cases_and_seed():
    cases=tuple(ConstitutionalCase('case_%03d'%i,('baseline','alternative'),'baseline',protected=(i%4==0)) for i in range(128))
    c=ConstitutionalSpec(cases,max_noncritical_changes=16)
    data={x.case_id:x.expected for x in cases}
    rng=random.Random(101)
    for i in rng.sample([i for i in range(128) if i%4], 16):data['case_%03d'%i]='alternative'
    assert assess_drift(c,data,trusted_spec_digest=c.digest)['status']=='PASS_FINITE_PROBE_UNATTESTED'
    for i in range(128):data['case_%03d'%i]='alternative'
    r=assess_drift(c,data,trusted_spec_digest=c.digest)
    assert r['status']=='REJECT' and r['protected_violations']==32


def test_const_011_composite_checks_real_polynomial_equivalence_and_policy():
    from omega_x_evolution.rsi_ir_guard import review_candidate
    p=Policy(); c=spec()
    a=Program(('add',('x',),('y',)))
    b=Program(('sub',('add',('x',),('y',)),('lit',0)))
    out=review_rsi_with_drift(a,b,p,p,c,baseline(),trusted_policy_digest=p.digest,trusted_spec_digest=c.digest)
    assert out['status']=='CANDIDATE_FOR_HUMAN_REVIEW'
    assert out['rsi']['status']=='PROVED_NARROW_INVARIANTS'
    assert out['release_authorized'] is False
    assert out['human_review_required'] is True
    changed=baseline();changed['critical_1']='allow'
    assert review_rsi_with_drift(a,b,p,p,c,changed,trusted_policy_digest=p.digest,trusted_spec_digest=c.digest)['status']=='REJECT'
    wrong=Program(('mul',('x',),('y',)))
    assert review_rsi_with_drift(a,wrong,p,p,c,baseline(),trusted_policy_digest=p.digest,trusted_spec_digest=c.digest)['status']=='REJECT'
    escalated=Policy(capabilities=('compiler','local_eval'))
    assert review_rsi_with_drift(a,b,p,escalated,c,baseline(),trusted_policy_digest=p.digest,trusted_spec_digest=c.digest)['status']=='REJECT'


def test_const_012_caller_supplied_observations_are_not_authoritative():
    c=spec()
    r=assess_drift(c,baseline(),trusted_spec_digest=c.digest)
    assert r['evidence_origin']=='CALLER_SUPPLIED_UNATTESTED'
    assert r['release_authorized'] is False
    assert r['human_values_alignment_proved'] is False


def test_const_013_resource_bounds_reject_excessive_input():
    cases=tuple(ConstitutionalCase('case_%d'%i,('x','y'),'x') for i in range(129))
    with pytest.raises(ValueError):ConstitutionalSpec(cases)
    with pytest.raises(ValueError):ConstitutionalSpec(())
    c=spec()
    too_big=baseline();too_big['pad']='A'*100000
    assert assess_drift(c,too_big,trusted_spec_digest=c.digest)['status']=='REJECT'
