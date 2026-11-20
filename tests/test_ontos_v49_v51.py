"""TDD: manifests, normalized beliefs, and quarantined bitemporal evidence."""
from dataclasses import FrozenInstanceError
from fractions import Fraction
from itertools import product
import hashlib
import math

import pytest

from omega_x_evolution.ontos_v49_manifest import (SOURCE_PATHS, SourceRecord,
                                                  audit_inventory)
from omega_x_evolution.ontos_v50_belief import BeliefFilter
from omega_x_evolution.ontos_v51_skepticism import MemoryEvent, review_evidence


def rec(path, content=None, decision='RESEARCH', license_id='UNKNOWN'):
    digest = hashlib.sha256(content).hexdigest() if content is not None else None
    return SourceRecord(path, digest, decision, 'Documented source traceability.', license_id)


def baseline_manifest():
    return tuple(rec(p) for p in SOURCE_PATHS)


def events(*, positive=True, n=5, tenant='tenantA', sha=None):
    if sha is None:
        sha=hashlib.sha256(b'audited synthetic source').hexdigest()
    cand=hashlib.sha256(b'candidate').hexdigest()
    return tuple(MemoryEvent(tenant, cand, f'event-{i}', f'group-{i}', sha, positive,
                            0, 100, 1) for i in range(n))


def test_v49_all_source_paths_are_exact_and_unique():
    assert len(SOURCE_PATHS)==33
    assert len(set(SOURCE_PATHS))==33
    assert SOURCE_PATHS[0]=='README.md'
    assert SOURCE_PATHS[-1]=='scripts/verify_all.sh'
    assert SOURCE_PATHS[12]=='src/omega_ontos/immune_kernel.py'


def test_v49_unverified_manifest_cannot_be_promoted():
    result=audit_inventory(baseline_manifest(), {})
    assert result['registered']==33
    assert result['checked_blobs']==0
    assert result['ready_for_integration'] is False
    assert len(result['unknown'])==33
    assert result['verified_digests']==()
    assert len(result['manifest_sha256'])==64
    assert audit_inventory(baseline_manifest(), {})==result


def test_v49_verifies_actual_bytes_only_and_is_order_independent():
    content=b'echo integration disabled\n'
    records=list(baseline_manifest())
    records[0]=rec(SOURCE_PATHS[0],content,'REUSE','Apache-2.0')
    out=audit_inventory(tuple(records),{SOURCE_PATHS[0]:content})
    assert out['checked_blobs']==1
    assert out['verified_digests']==(hashlib.sha256(content).hexdigest(),)
    assert out['ready_for_integration'] is False
    assert audit_inventory(tuple(reversed(records)),{SOURCE_PATHS[0]:content})==out


def test_v49_mismatched_bytes_do_not_pass():
    records=list(baseline_manifest())
    records[0]=rec(SOURCE_PATHS[0],b'original','PORT','MIT')
    with pytest.raises(ValueError,match='digest'):
        audit_inventory(tuple(records),{SOURCE_PATHS[0]:b'changed'})


@pytest.mark.parametrize('path', ['../escape.py','src//bad.py','/tmp/x','src/../README.md',
                                  'src\\evil.py','not-on-manifest.py','README.md\nxx'])
def test_v49_rejects_unsafe_or_unknown_paths(path):
    with pytest.raises(ValueError):
        rec(path)


def test_v49_rejects_duplicate_alias_missing_extra_payload_and_bad_license():
    with pytest.raises(ValueError): audit_inventory(baseline_manifest()[:-1],{})
    with pytest.raises(ValueError): audit_inventory(baseline_manifest()[:-1]+(baseline_manifest()[0],),{})
    with pytest.raises(ValueError): audit_inventory(baseline_manifest(),{'anything':b'data'})
    with pytest.raises(ValueError): SourceRecord('README.md','f'*64,'PORT','good reason','UNKNOWN')
    with pytest.raises(ValueError): SourceRecord('README.md',None,'PORT','good reason','MIT')
    with pytest.raises(ValueError): SourceRecord('README.md',None,'RESEARCH','  ','UNKNOWN')
    with pytest.raises(ValueError): SourceRecord('README.md',None,'RESEARCH','ok','my-secret-license')
    with pytest.raises(ValueError): audit_inventory(baseline_manifest(),{'README.md':b'a'*65537})


def test_v49_not_a_source_executor():
    result=audit_inventory(baseline_manifest(),{})
    assert 'module' not in result and 'compiled' not in result
    with pytest.raises(FrozenInstanceError):
        baseline_manifest()[0].path='modified'


@pytest.mark.parametrize('prior,likelihood,expected', [
    ((.5,.5), (1.,1.),(.5,.5)),
    ((.5,.5), (1.,0.),(1.,0.)),
    ((.5,.5), (0.,1.),(0.,1.)),
])
def test_v50_normalization_with_post_floor(prior,likelihood,expected):
    result=BeliefFilter(prior_mix=0.,floor=1e-4).update(prior,likelihood)
    assert math.fsum(result.posterior)==pytest.approx(1.,abs=1e-15)
    assert all(p>=1e-4 for p in result.posterior)
    assert result.posterior[0]>result.posterior[1] if expected[0]>expected[1] else result.posterior[0]<=result.posterior[1]


def test_v50_exact_boundary_floor():
    result=BeliefFilter(prior_mix=0.,floor=1e-4).update((.5,.5),(1.,0.))
    assert result.posterior[1]==pytest.approx(1e-4,abs=1e-15)
    assert result.posterior[0]==pytest.approx(1.-1e-4,abs=1e-15)
    assert result.abstain is False


def test_v50_zero_likelihood_abstains_and_keeps_legal_distribution():
    r=BeliefFilter().update((.1,.9),(0.,0.))
    assert r.abstain and r.log_evidence is None and r.surprise_bits is None
    assert math.fsum(r.posterior)==pytest.approx(1)
    assert all(p>=1e-4 for p in r.posterior)


def test_v50_tiny_likelihoods_do_not_underflow_to_abstention():
    r=BeliefFilter().update((.5,.5),(5e-324,0.))
    assert not r.abstain
    assert math.isfinite(r.log_evidence)
    assert math.isfinite(r.surprise_bits)
    assert min(r.posterior)>=1e-4


def test_v50_zero_prior_can_recover_after_regime_shift():
    model=BeliefFilter(prior_mix=.06,floor=.0001)
    prior=(1.,0.,0.,0.)
    for step in range(240):
        active=(step//60)%4
        likelihood=tuple(1. if i==active else .001 for i in range(4))
        prior=model.update(prior,likelihood).posterior
        assert math.fsum(prior)==pytest.approx(1,abs=1e-14)
        assert all(math.isfinite(p) and p>=.0001 for p in prior)
    assert prior[3]>.9


def test_v50_seed_9274_long_trace_is_deterministic():
    import random
    def run():
        rng=random.Random(9274)
        prior=(.25,)*4
        m=BeliefFilter()
        for _ in range(240):
            likelihood=tuple(rng.random() if rng.randrange(8) else 0. for _ in range(4))
            prior=m.update(prior,likelihood).posterior
        return prior
    assert run()==run()
    assert min(run())>=1e-4


@pytest.mark.parametrize('prior,like,kwargs', [
    ((.5,.5),(-1.,1.),{}),((float('nan'),.5),(.5,.5),{}),
    ((.4,.4),(.1,.1),{}),((.5,.5),(.5,),{}),
    ((.5,.5),(.5,True),{}),((1.,), (1.,), {}),
    ((.5,.5),(.5,.5),{'floor':.5}),
    ((.5,.5),(.5,.5),{'prior_mix':True}),
    ((.5,.5),(.5,.5),{'prior_mix':-1}),
])
def test_v50_rejects_malformed_probability_contract(prior,like,kwargs):
    with pytest.raises(ValueError):
        BeliefFilter(**kwargs).update(prior,like)


def test_v50_bayesian_reference_oracle_with_decimal():
    from decimal import Decimal, localcontext
    with localcontext() as c:
        c.prec=60
        prior=(Decimal('0.2'),Decimal('0.8'))
        likelihood=(Decimal('0.01'),Decimal('0.7'))
        mass=[p*l for p,l in zip(prior,likelihood)]
        normalized=[x/sum(mass) for x in mass]
        f=Decimal('0.0001')
        expected=[f+(1-2*f)*x for x in normalized]
    r=BeliefFilter(prior_mix=0.,floor=.0001).update((.2,.8),(.01,.7))
    assert r.posterior==pytest.approx(tuple(map(float,expected)),rel=1e-13)


def test_v50_effective_belief_bounds():
    r=BeliefFilter().update((.25,)*4,(1.,)*4)
    assert r.effective_classes==pytest.approx(4.)
    r2=BeliefFilter().update((.25,)*4,(0.,0.,0.,1.))
    assert 1 <= r2.effective_classes < 2


def test_v51_all_verified_independent_evidence_is_only_manual_eligibility():
    rows=events(n=5)
    digest=rows[0].source_sha256
    a=review_evidence(rows,tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                      valid_at=50,known_at=1,verified_sources=frozenset((digest,)))
    assert a['e_value']==Fraction(32)
    assert a['eligible_for_manual_review'] is True
    assert a['decision']=='QUARANTINED_REVIEW_ONLY'
    assert a['independence_verified'] is False
    assert a['evidence_count']==5 and len(a['source_digests'])==1


def test_v51_unverified_origin_and_conflicting_evidence_fail_closed():
    rows=events(n=5)
    a=review_evidence(rows,tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                      valid_at=50,known_at=1,verified_sources=frozenset())
    assert a['eligible_for_manual_review'] is False
    assert a['decision']=='QUARANTINE_UNVERIFIED_SOURCE'
    assert a['e_value']==Fraction(32)
    with pytest.raises(ValueError,match='independence'):
        r=rows[0]
        review_evidence((r, MemoryEvent(r.tenant,r.candidate_sha256,'other',r.group,r.source_sha256,
                                      False,0,100,1)),tenant=r.tenant,candidate_sha256=r.candidate_sha256,
                        valid_at=30,known_at=1,verified_sources=frozenset((r.source_sha256,)))


def test_v51_bitemporal_retraction_and_known_at_boundary():
    row=events(n=5)
    old=row[-1]
    retract=MemoryEvent(old.tenant,old.candidate_sha256,old.ident,old.group,
                        old.source_sha256,None,0,100,5)
    kwargs=dict(tenant='tenantA',candidate_sha256=old.candidate_sha256,valid_at=50,
                verified_sources=frozenset((old.source_sha256,)))
    before=review_evidence(row+(retract,),known_at=4,**kwargs)
    after=review_evidence(row+(retract,),known_at=5,**kwargs)
    assert before['evidence_count']==5 and before['eligible_for_manual_review']
    assert after['evidence_count']==4 and not after['eligible_for_manual_review']
    assert after['e_value']==Fraction(16)
    assert review_evidence(row+(retract,),known_at=5,valid_at=150,tenant='tenantA',
                           candidate_sha256=old.candidate_sha256,
                           verified_sources=frozenset((old.source_sha256,)))['evidence_count']==0


def test_v51_bitemporal_correction_suppresses_old_record():
    rows=events(n=5)
    r=rows[0]
    correction=MemoryEvent(r.tenant,r.candidate_sha256,r.ident,r.group,
                           r.source_sha256,False,40,80,3)
    kwargs=dict(tenant='tenantA',candidate_sha256=r.candidate_sha256,valid_at=30,
                verified_sources=frozenset((r.source_sha256,)))
    before=review_evidence(rows+(correction,),known_at=2,**kwargs)
    after=review_evidence(rows+(correction,),known_at=3,**kwargs)
    assert before['e_value']==Fraction(32)
    assert after['evidence_count']==4 and after['e_value']==Fraction(16)


def test_v51_out_of_order_storage_and_replay_are_identical():
    rows=events(n=6)
    kwargs=dict(tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,valid_at=1,
                known_at=2,verified_sources=frozenset((rows[0].source_sha256,)))
    assert review_evidence(rows,**kwargs)==review_evidence(rows[::-1],**kwargs)
    assert review_evidence(rows,**kwargs)['e_value']==Fraction(64)


def test_v51_false_consolidation_cases_9216_9651():
    for seed in (9216,9651):
        rows=events(n=5)
        correction=MemoryEvent(rows[0].tenant,rows[0].candidate_sha256,rows[0].ident,
                               rows[0].group, rows[0].source_sha256,False,0,100,seed)
        kwargs=dict(tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,valid_at=20,
                    known_at=seed, verified_sources=frozenset((rows[0].source_sha256,)))
        result=review_evidence(rows+(correction,),**kwargs)
        assert not result['eligible_for_manual_review']
        assert result['e_value']==Fraction(32,3)
        assert result['decision']=='QUARANTINED_REVIEW_ONLY'


def test_v51_no_cross_tenant_or_invalid_sha():
    rows=events(n=5)
    one=rows[0]
    wrong=MemoryEvent('tenantB',one.candidate_sha256,'other','other',one.source_sha256,
                       True,0,100,1)
    with pytest.raises(ValueError,match='tenant'):
        review_evidence(rows+(wrong,),tenant='tenantA',candidate_sha256=one.candidate_sha256,
                        valid_at=1,known_at=1,verified_sources=frozenset((one.source_sha256,)))
    with pytest.raises(ValueError):
        MemoryEvent('tenantA','invalid','a','g','f'*64,True,0,100,1)


def test_v51_ambiguous_transaction_rejected():
    row=events(n=1)[0]
    conflicting=MemoryEvent(row.tenant,row.candidate_sha256,row.ident,row.group,
                           row.source_sha256,False,0,100,1)
    with pytest.raises(ValueError,match='ambiguous'):
        review_evidence((row,conflicting),tenant=row.tenant,candidate_sha256=row.candidate_sha256,
                        valid_at=20,known_at=1,verified_sources=frozenset((row.source_sha256,)))


def test_v51_no_automatic_acceptance_or_mutation():
    rows=events(n=6)
    result=review_evidence(rows,tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                           valid_at=50,known_at=1,
                           verified_sources=frozenset((rows[0].source_sha256,)))
    assert not any('accept' in k or 'promote' in k for k in result)
    assert rows==events(n=6)
    with pytest.raises(FrozenInstanceError):
        rows[0].positive=False


def test_v49_v51_manifest_verified_digest_to_manual_memory_review():
    payload=b'audited synthetic source'
    records=list(baseline_manifest())
    records[0]=rec(SOURCE_PATHS[0],payload,'REUSE','MIT')
    manifest=audit_inventory(tuple(records),{SOURCE_PATHS[0]:payload})
    rows=events(n=5,sha=hashlib.sha256(payload).hexdigest())
    state=review_evidence(rows,tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                          valid_at=50,known_at=1,
                          verified_sources=frozenset(manifest['verified_digests']))
    assert state['eligible_for_manual_review']
    assert state['decision']=='QUARANTINED_REVIEW_ONLY'


def test_v50_v51_contract_does_not_feed_truth_into_belief():
    rows=events(n=5)
    v=review_evidence(rows,tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                      valid_at=50,known_at=1,verified_sources=frozenset())
    belief=BeliefFilter().update((.5,.5),(.2,.7))
    assert v['decision']=='QUARANTINE_UNVERIFIED_SOURCE'
    assert math.fsum(belief.posterior)==pytest.approx(1)
    assert not hasattr(belief,'accepted')


def test_v49_mutated_manifest_metadata_is_revalidated():
    rows = list(baseline_manifest())
    object.__setattr__(rows[0], 'path', '../outside')
    with pytest.raises(ValueError):
        audit_inventory(tuple(rows), {})


def test_v50_mutated_filter_config_is_revalidated():
    model=BeliefFilter()
    model.prior_mix=float('nan')
    with pytest.raises(ValueError):
        model.update((.5,.5),(.5,.5))


def test_v51_mutated_event_is_revalidated():
    rows=list(events(n=1))
    object.__setattr__(rows[0], 'source_sha256', 'invalid')
    with pytest.raises(ValueError):
        review_evidence(tuple(rows),tenant='tenantA',candidate_sha256=rows[0].candidate_sha256,
                        valid_at=1,known_at=1,verified_sources=frozenset())


def test_v51_conflicting_independence_group_prevents_promotion():
    rows = list(events(n=5))
    original=rows[1]
    rows[1]=MemoryEvent(original.tenant, original.candidate_sha256,original.ident,
                        rows[0].group,original.source_sha256,True,0,100,1)
    with pytest.raises(ValueError, match='independence'):
        review_evidence(tuple(rows),tenant='tenantA',
                        candidate_sha256=rows[0].candidate_sha256,valid_at=50,known_at=1,
                        verified_sources=frozenset((rows[0].source_sha256,)))


def test_v49_full_matched_sha_only_allows_review_not_integration():
    blob=b'synthetic source content - not inspected'
    sources={p:blob for p in SOURCE_PATHS}
    records=tuple(rec(p,blob,'REUSE','Apache-2.0') for p in SOURCE_PATHS)
    result=audit_inventory(records,sources)
    assert result['registered']==33 and result['checked_blobs']==33
    assert result['eligible_for_manual_review'] is True
    assert result['ready_for_integration'] is False


def test_v49_restrict_license_for_manual_review():
    blob=b'synthetic license fixtures'
    sources={p:blob for p in SOURCE_PATHS}
    records=tuple(rec(p,blob,'REUSE','Proprietary') for p in SOURCE_PATHS)
    result=audit_inventory(records,sources)
    assert result['checked_blobs']==33
    assert result['eligible_for_manual_review'] is False
    assert result['ready_for_integration'] is False


def test_v49_checked_in_manifest_matches_exact_33_source_register():
    from pathlib import Path
    import json
    root=Path(__file__).resolve().parents[1]
    payload=json.loads((root/'docs/omega/V49_SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    assert payload['schema']=='ontos-source-register-v49-v1'
    assert payload['source_sha256']=='95c2794d9a3b5e237781b296b2aa6da0b6cdb174d6a73e5f754f48e7264edc36'
    rows=tuple(SourceRecord(**entry) for entry in payload['entries'])
    result=audit_inventory(rows,{})
    assert result['registered']==33 and result['checked_blobs']==0
    assert result['ready_for_integration'] is False
    assert result['manifest_sha256']==payload['entry_digest_sha256']


def test_v50_nonstationary_30_seed_campaign_is_bounded_and_reproducible():
    import random, hashlib, json
    def replay(seed):
        rng=random.Random(seed)
        state=(.25,)*4
        history=[]
        for t in range(240):
            reg=(0,1,2,0)[t//60]
            likelihood=tuple((.1+(.9 if i==reg else 0.))*rng.random() for i in range(4))
            if t%31==0:
                likelihood=(0.,)*4
            result=BeliefFilter(prior_mix=.06,floor=.0001).update(state,likelihood)
            state=result.posterior
            assert all(math.isfinite(x) and x>=.0001 for x in state)
            assert math.fsum(state)==pytest.approx(1.,abs=1e-14)
            history.append((state,result.abstain))
        return hashlib.sha256(json.dumps(history,allow_nan=False,separators=(',',':')).encode()).hexdigest()
    seeds=tuple(9100+29*i for i in range(30))
    first=tuple(replay(s) for s in seeds)
    assert len(set(first))==30
    assert first==tuple(replay(s) for s in seeds)
