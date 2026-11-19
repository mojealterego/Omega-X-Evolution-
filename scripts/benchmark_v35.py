"""Reproducible bounded discovery, LoRA and local process evidence."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
from omega_x_evolution.axioms import discover, verify, structures
from omega_x_evolution.plasticity import Policy, fixture, Plasticity, evaluate_adapter, choose
from omega_x_evolution.infrastructure import Limits, Job, Orchestrator
from omega_x_evolution.engine import BASELINE


def main():
    d=discover(seed=42,budget=256)
    assert verify(d)
    algebra=structures(3)
    assert algebra['exhaustive']
    t,v,r,test=fixture(42,groups=4)
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        p=Policy(seed=42,rank=2,steps=400,max_updates=2)
        bank=Plasticity(root/'plastic.db',b'p'*32,p,create=True)
        fit=bank.update(t,v,r,authorized=True,request_id='trial')
        assert bank.update(t,v,r,authorized=True,request_id='trial')==fit
        heldout=evaluate_adapter(p,fit['adapter'],test)
        proposal=choose(p,fit['adapter'],BASELINE,42)
        state=bank.rollback(authorized=True)
        limits=Limits(total_cpu_seconds=15,max_jobs=3,max_parallel=2)
        s=Orchestrator(root/'infra.db',b'i'*32,limits,create=True)
        jobs=(Job('axioms','axioms',5,10,budget=256),Job('scheduler','scheduler',5,10,budget=64),Job('plasticity','plasticity',5,10,budget=400))
        results=s.run_batch(jobs,authorized=True)
        assert all(x['status']=='succeeded' for x in results)
        assert s.run_batch(jobs,authorized=True)==results
        ledger=s.inspect()
        s.stop(authorized=True)
        assert s.inspect()['stopped']
        out={'discovery':{'seed':d['seed'],'budget':d['budget'],'grammar_programs':d['grammar_programs'],'proposals':d['proposals'],**{k:len(d[k]) for k in ('proved','refuted','unknown')},'sample_proof':d['proved'][0],'sample_counterexample':d['refuted'][0],'replay_verified':True},'finite_algebra':{k:v for k,v in algebra.items() if k!='models'},'plasticity':{'fit':fit,'test':heldout,'proposal':proposal,'rows_per_split':[len(x) for x in (t,v,r,test)],'rollback_verified':state['active']==state['initial'],'used_steps_after_rollback':state['used_steps']},'infrastructure':{'reserved_cpu_seconds':ledger['reserved_cpu_seconds'],'peak_parallel':ledger['last_peak_parallel'],'unique_child_processes':len({x['pid'] for x in results}),'jobs':[{'kind':x['job']['kind'],'status':x['status'],'exit_code':x['exit_code'],'wall_seconds':x['wall_seconds']} for x in results],'idempotent_replay':True,'stop_marker':True}}
    print(json.dumps(out,indent=2,allow_nan=False))

if __name__=='__main__':main()
