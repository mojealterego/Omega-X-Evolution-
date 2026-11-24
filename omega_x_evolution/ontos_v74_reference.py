"""Deterministic reference A-D campaign, not reconstruction of source identities.

Public fixture keys and salts qualify protocol mechanics only. A/B score fixed
replay tapes, C scores feature-only binary predictions through v73, and D
executes the existing v62 noise model. No candidate code is executed.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
import argparse
import math

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from .ontos_testbed import replay
from .ontos_v62_noise import simulate_error
from .ontos_v72_jcs import canonical_json
from .ontos_v73_holdout import Candidate, HoldoutPlan, HoldoutBroker, label_commitment, submission_bytes, seal_bytes
from .ontos_v74_campaign import CampaignPlan, Configuration, Run, analyze_campaign

SEEDS = tuple(9100 + 29*i for i in range(30))
TRIALS = 240
_MODULES = ('ontos_testbed.py','ontos_v62_noise.py','ontos_v72_jcs.py',
            'ontos_v72_receipts.py','ontos_v73_holdout.py','ontos_v74_campaign.py',
            'ontos_v74_reference.py')


def digest(value):
    return sha256(canonical_json(value)).hexdigest()


def parameters(suite, index):
    if suite in 'AB':
        return {'offset':index%3,'period':(1,3,7)[index//3] if index<9 else 1,
                'abstain_every':0 if index<9 else index-7,'mode':suite}
    if suite=='C':
        return {'threshold':2.0+0.25*(index if index<9 else index-9),
                'drop_feature':None if index<9 else index-9}
    if suite=='D':
        return {'p':(.1,.2,.3)[index//3] if index<9 else .25,
                'correlation':(0.,.25,.75)[index%3] if index<9 else (0.,.75)[(index-9)//3],
                'rechecks':3 if index<9 else (0,1,2)[(index-9)%3]}
    raise ValueError('unknown reference suite')


def reference_plan() -> CampaignPlan:
    root = Path(__file__).resolve().parent
    protocol = digest({name:sha256((root/name).read_bytes()).hexdigest() for name in _MODULES})
    configs = tuple(Configuration(f'{s}{i:02}',s,'PRIMARY' if i<9 else 'ABLATION',
                     'REFERENCE-v74',TRIALS,digest({'protocol':protocol,'parameters':parameters(s,i)}))
                    for s in 'ABCD' for i in range(15))
    comparisons = tuple((f'{s}{i:02}',f'{s}00') for s in 'ABCD' for i in (1,4,8,9,14))
    return CampaignPlan(SEEDS,configs,comparisons,7412,protocol)


def _fixture_key(name):
    return Ed25519PrivateKey.from_private_bytes(sha256(('PUBLIC-SIMULATION-ONLY:'+name).encode()).digest())


def _pub(key):
    return key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)


def _tape(p):
    return tuple(5 if p['abstain_every'] and (t+1)%p['abstain_every']==0 else
                 ((t//p['period'] if p['mode']=='A' else t//60+t//p['period'])+p['offset'])%4
                 for t in range(TRIALS))


def predict(features: tuple[tuple[float, ...], ...], p: dict) -> tuple[int, ...]:
    """Feature-only norm threshold; no labels, broker or scored rows received."""
    return tuple(int(math.sqrt(math.fsum(x*x for j,x in enumerate(row)
                    if j!=p['drop_feature']))>p['threshold']) for row in features)


def execute_seed(plan: CampaignPlan, seed: int) -> tuple[tuple[Run,...],tuple[dict,...]]:
    if type(plan) is not CampaignPlan or plan.digest()!=reference_plan().digest() or type(seed) is not int or seed not in plan.seeds:
        raise ValueError('unregistered reference plan or seed')
    runs, details = [], []
    def add(c, row):
        detail = {'configuration':c.name,'suite':c.suite,'seed':seed,**row}
        runs.append(Run(c.name,seed,'COMPLETED',row['correct'],digest(detail)))
        details.append(detail)
    # Evaluate all C candidates on the same feature cohort before releasing scores.
    scored = replay(seed, (0,1,2,3)*60)
    features = tuple(r.observation.continuous for r in scored)
    truth = tuple(int(r.ood) for r in scored)
    cohort = tuple(c for c in plan.configurations if c.suite=='C')
    keys = {c.name:_fixture_key(c.name) for c in cohort}
    ext = _fixture_key('external')
    salt = sha256(f'PUBLIC-SIMULATION-SALT:{seed}'.encode()).digest()
    holdout = HoldoutPlan('reference',f'C-{seed}',plan.digest(),digest([list(x) for x in features]),
        TRIALS,label_commitment(truth,salt),tuple(Candidate(c.name,c.artifact_sha256,_pub(keys[c.name])) for c in cohort),_pub(ext))
    broker = HoldoutBroker(holdout,truth,salt)
    predictions = {}
    for c in cohort:
        values = predict(features,parameters('C',int(c.name[1:])))
        message = submission_bytes(broker.plan_digest,c.name,values)
        signature = keys[c.name].sign(message)
        if broker.submit(c.name,values,signature)!='ACCEPTED' or broker.report() is not None:
            raise RuntimeError('holdout admission failed')
        predictions[c.name] = digest({'predictions':list(values),'signature':signature.hex()})
    if broker.seal(ext.sign(seal_bytes(broker.plan_digest)))!='SEALED':
        raise RuntimeError('holdout seal failed')
    report = broker.report()
    if report is None:
        raise RuntimeError('missing sealed report')
    for c in plan.configurations:
        p = parameters(c.suite,int(c.name[1:]))
        if c.suite in 'AB':
            rows = replay(seed,_tape(p))
            trace = [asdict(r) for r in rows]
            for row in trace:
                row['observation']['continuous'] = list(row['observation']['continuous'])
            add(c,{'correct':sum(r.correct for r in rows),'harm':sum(r.harm for r in rows),
                   'abstained':sum(r.action==5 for r in rows),'trace_sha256':digest(trace)})
        elif c.suite=='C':
            r = report['candidates'][c.name]
            if r['status']!='SCORED' or r['total']!=TRIALS:
                raise RuntimeError('incomplete holdout report')
            add(c,{'correct':r['correct'],'incorrect':r['incorrect'],'abstained':r['abstained'],
                   'broker_plan_sha256':broker.plan_digest,'broker_report_sha256':digest(report),
                   'submission_sha256':predictions[c.name]})
        else:
            r = simulate_error(seed,trials=TRIALS,**p)
            add(c,{'correct':TRIALS-r['false_accepts'],'false_accepts':r['false_accepts'],
                   'modeled_checks':r['modeled_checks'],'simulation_sha256':digest(r)})
    return tuple(runs),tuple(details)


def run_reference(pinned_digest: str) -> dict:
    plan = reference_plan()
    if plan.digest()!=pinned_digest:
        raise ValueError('reference preregistration mismatch')
    runs, details = [], []
    for seed in plan.seeds:
        r,d = execute_seed(plan,seed)
        runs.extend(r); details.extend(d)
    report = analyze_campaign(plan,pinned_digest,tuple(runs))
    return {'schema':'omega-v74-reference-execution-v1','verification_mode':'HYBRID',
            'test_keys_only':True,'plan_sha256':pinned_digest,'report':report,
            'records':[asdict(r) for r in runs],'details':details,'release_authorized':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pin')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    if args.pin is None and args.output is None:
        print(reference_plan().digest()); return
    if args.pin is None or args.output is None:
        parser.error('--pin and --output are both required for execution')
    result = run_reference(args.pin)
    # Per-run evidence is a large file: encode individual bounded JCS records.
    import json
    with args.output.open('x',encoding='utf-8') as f:
        json.dump(result,f,sort_keys=True,separators=(',',':'),allow_nan=False)
        f.write('\n')


if __name__=='__main__':
    main()
