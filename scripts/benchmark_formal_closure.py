"""Executable acceptance experiment for closure of requirements 1–4."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import tempfile
import time
from omega_x_evolution.safety_synthesis import prove,verify,RuleBook
from omega_x_evolution.modal import prove_k
from omega_x_evolution.cluster import ClusterConfig,Store,LocalBackend,run_cluster
from omega_x_evolution.engine import Cascade


def demo():
    sources=('-(x+y)','-(x+y+abs(x-y)/(.01+x*y))','min(abs(x-y),1)','1/(.25+x)','2/(.25+x)','1/(x-.123456)','1e6*1e6*1e6','__import__("os")')
    records=[];book=RuleBook()
    for code in sources:
        t=time.perf_counter();p=prove(code);elapsed=time.perf_counter()-t
        matches=book.matches(code) if p['proved'] else []
        if p['proved']:book.learn(code,p)
        records.append({'source':code,'proved':p['proved'],'verified':verify(code,p),'reason':p['reason'],'boxes':p['boxes'],'obligations':p['obligations'],'independent':p['independent'],'modal_worlds':p['modal']['worlds'] if p['modal'] else None,'tableau_nodes':p['modal']['k_proof']['tableau_nodes'] if p['modal'] else None,'prior_rule_matches':matches,'stage':Cascade(42).evaluate(code).stage,'seconds':elapsed})
    p=('atom','p');q=('atom','q')
    theorem=('implies',('box',('implies',p,q)),('implies',('box',p),('box',q)))
    return {'cases':records,'learned_rules':book.count,'general_k':prove_k(theorem),'invalid_k':prove_k(('implies',('box',p),p)),'bounded_unknown':prove_k(theorem,budget=1)}


def campaign(path):
    cfg=ClusterConfig(islands=4,rounds=2,batch=4,budget=32,parallelism=2,migration_interval=1,formal_safety=True)
    store=Store(path,b't'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as backend:
        first=asyncio.run(run_cluster(store,backend,stop_after=3))
    with LocalBackend(cfg,processes=True) as backend:
        final=asyncio.run(run_cluster(store,backend));repeat=asyncio.run(run_cluster(store,backend))
    rules=[];proof_count=0;obligations=0
    for i in range(cfg.islands):
        _,s=store.read(i);rules.append(RuleBook(s['safety_rules']).count)
        proof_count+=len(s['formal_records']);obligations+=sum(r['certificate']['obligations'] for r in s['formal_records'])
        assert all(verify(a['code'],prove(a['code'])) for a in s['lineage'])
    assert final==repeat and final['complete'] and final['attempts']==32
    return {'first_commit_count':first['commits'],'complete':final,'durable_replay':final==repeat,'retained_rule_counts':rules,'certificate_records':proof_count,'checked_numeric_obligations':obligations}


def main():
    with tempfile.TemporaryDirectory() as d:
        print(json.dumps({'formal':demo(),'campaign':campaign(Path(d)/'islands.db')},indent=2,allow_nan=False))

if __name__=='__main__':main()
