"""Offline Phase0 incident-style snapshots: 9216, 9274, 9651.

Truth and observation diagnostics are separate. Replays are the project's
real fixed-action testbed, not the original Argon organism from its PDF.
JSON stdout is deterministic and contains synthetic data only.
"""
from dataclasses import asdict
from fractions import Fraction
import hashlib
import json

from omega_x_evolution.ontos_testbed import replay
from omega_x_evolution.ontos_v50_belief import BeliefFilter
from omega_x_evolution.ontos_v51_skepticism import MemoryEvent, review_evidence

SEEDS=(9216,9274,9651)
ACTIONS=(0,1,2,3)*60
CANDIDATE=hashlib.sha256(b'ontos-synthetic-attractor').hexdigest()
SOURCE=hashlib.sha256(b'ontos-synthetic-source').hexdigest()


def observe_only(observations):
    """Accept ONLY observation values, never ScoredStep or scorer truth."""
    filt=BeliefFilter(prior_mix=.06,floor=1e-4)
    prior=(.25,)*4
    events=[]
    for obs in observations:
        likelihood=tuple(.9 if j==obs.discrete else .1 for j in range(4))
        out=filt.update(prior,likelihood)
        prior=out.posterior
        events.append({'step':obs.step,'discrete':obs.discrete,'tamper':obs.tamper,
                       'lure':obs.lure,'damage':obs.damage,'posterior':prior,
                       'effective_classes':out.effective_classes,'abstain':out.abstain})
    return events


def memory_attack_probe(seed):
    """Explicitly injected synthetic poison, not an observed Argon incident."""
    if seed not in SEEDS: raise ValueError('registered seed required')
    events=tuple(MemoryEvent('Phase0',CANDIDATE,f'e-{i}',f'group-{i}',SOURCE,
                             True,0,240,1) for i in range(5))
    retract=MemoryEvent('Phase0',CANDIDATE,'e-0','group-0',SOURCE,
                        False,0,240,seed)
    args={'tenant':'Phase0','candidate_sha256':CANDIDATE,'valid_at':120,
          'verified_sources':frozenset((SOURCE,))}
    pre=review_evidence(events+(retract,),known_at=1,**args)
    post=review_evidence(events+(retract,),known_at=seed,**args)
    return {'scenario':'SYNTHETIC_INJECTED_BITEMPORAL_CORRECTION',
            'pre_e_value':str(pre['e_value']),
            'post_e_value':str(post['e_value']),
            'pre_eligible_for_manual_review':pre['eligible_for_manual_review'],
            'post_eligible_for_manual_review':post['eligible_for_manual_review'],
            'decision':post['decision'],'automatic_promotion':False}


def report():
    records=[]
    for seed in SEEDS:
        scored=replay(seed,ACTIONS)
        public=tuple(x.observation for x in scored)
        observed=observe_only(public)
        # Raw full traces retained for replay; expected failures are not hidden.
        truth=[{'step':x.observation.step,'regime':x.regime,'ood':x.ood,
                'correct':x.correct,'true_state':x.true_state,'action':x.action,
                'harm':x.harm,'next_state':x.next_state,'energy_gain':x.energy_gain}
               for x in scored]
        canonical=json.dumps([asdict(x) for x in scored],sort_keys=True,
                             separators=(',',':'),allow_nan=False).encode('utf-8')
        minbelief=min(min(x['posterior']) for x in observed)
        records.append({'seed':seed,'fixed_tape':'[0,1,2,3] x 60',
                        'source':'omega_x_evolution.ontos_testbed.replay',
                        'trace_sha256':hashlib.sha256(canonical).hexdigest(),
                        'observation_count':len(observed),'scorer_count':len(truth),
                        'correct':sum(x['correct'] for x in truth),
                        'ood':sum(x['ood'] for x in truth),
                        'lure_count':sum(x['lure'] for x in observed),
                        'tamper_count':sum(x['tamper'] for x in observed),
                        'minimum_belief':minbelief,
                        'floor_preserved':minbelief >= 1e-4-1e-15,
                        'synthetic_memory_probe':memory_attack_probe(seed),
                        'observations_only':observed,'scorer_only':truth})
    return {'schema':'ontos-phase0-diagnostic-seeds-v1',
            'not_original_argon_failures':True,
            'truth_and_observations_separated_by_interface':True,
            'operator_actions_enabled':False,'rows':records}


if __name__=='__main__':
    print(json.dumps(report(),sort_keys=True,indent=2,allow_nan=False))
