import asyncio
import copy
import math
import random
import pytest
from omega_x_evolution.topology import TopologicalArchive, Manifold, TopologyPolicy, phenotype
from omega_x_evolution.engine import Artifact, Genome, Cascade, score
from omega_x_evolution.cluster import ClusterConfig, IslandActor, initial_state, verify_transition, ClusterError, Store, LocalBackend, run_cluster

CODES=['-(x+y)', '-(x+y+1)', '-(x+y+abs(x-y))', '-(x+y+(x-y)*(x-y))', '-(x+y+abs(x-y)/(x+y+0.1))', '-(x+y+(x-y)*(x-y)/(0.1+x*y)+2)', '-(x+y+(x-y)*(x-y)/(0.1+min(x,y))+2)', '-(x+y+abs(x-y)+max(x,y)+min(x,y))']

def archive():
    a=TopologicalArchive(TopologyPolicy(split_count=2, window=32)); c=Cascade(42)
    for i,code in enumerate(CODES):
        a.add(Artifact(str(i),str(i-1) if i else None,0,i,code,Genome(),c.evaluate(code).metrics))
    a.adapt();return a

def test_metric_spd_and_distance_axioms():
    a=archive();m=a.manifold
    for xx,xy,yy in m.tensors.values():
        assert xx>0 and yy>0 and xx*yy-xy*xy>0
    p,q,r=[phenotype(code,m.size) for code in (CODES[0],CODES[3],CODES[-1])]
    assert m.distance(p,p)==0
    assert m.distance(p,q)>0 and m.distance(p,q)==pytest.approx(m.distance(q,p))
    assert m.distance(p,r)<=m.distance(p,q)+m.distance(q,r)+1e-12
    assert len(set(m.tensors.values()))>1

def test_adaptive_partition_preserves_lineage_and_champion():
    a=archive(); assert len(a.manifold.leaves)>1
    assert len(a.lineage)==len(CODES)
    assert a.best().id==max(a.lineage.values(),key=lambda x:(score(x.metrics),x.id)).id
    assert all(len(c)<=4 for c in a.cells[0].values())
    assert all(a.manifold.cell(phenotype(x.code,a.manifold.size))==k for k,c in a.cells[0].items() for x in c)
    before=a.summary();a.adapt();assert a.summary()==before
    assert a.sample(0,random.Random(1)).id in a.lineage

def test_stagnant_region_coarsens():
    p=TopologyPolicy(split_count=2,window=8)
    diverse=Manifold(p,CODES)
    stagnant=Manifold(p,[CODES[0]]*8)
    assert len(diverse.leaves)>len(stagnant.leaves)==1

def test_cluster_integration_and_tamper(tmp_path):
    cfg=ClusterConfig(islands=2,rounds=2,batch=4,budget=16,parallelism=2,topology=TopologyPolicy(split_count=2))
    s=initial_state(cfg,0); actor=IslandActor(cfg,0); n=actor.step(s,None,s['elite'])
    verify_transition(cfg,s,n,None,s['elite'],False)
    assert n['topology']['leaf_count']>=1
    forged=copy.deepcopy(n);forged['topology']['leaf_count']+=1
    with pytest.raises(ClusterError):verify_transition(cfg,s,forged,None,s['elite'],False)
    db=Store(tmp_path/'state.db',b'k'*32,cfg).initialize()
    with LocalBackend(cfg,processes=True) as b:
        first=asyncio.run(run_cluster(db,b,stop_after=2)); assert not first['complete']
    with LocalBackend(cfg,processes=True) as b:
        final=asyncio.run(run_cluster(db,b));assert final['complete'] and final['attempts']==16
        assert final['topology']['leaf_count']>=2
        assert final==asyncio.run(run_cluster(db,b))

def test_policy_rejects_bad_parameters():
    for kwargs in ({'depth':0},{'depth':6},{'window':0},{'strength':float('nan')},{'split_count':1}):
        with pytest.raises(ValueError):TopologyPolicy(**kwargs)

def test_curvature_constant_and_variable_metric():
    flat=Manifold(TopologyPolicy(strength=0),CODES)
    curved=Manifold(TopologyPolicy(),CODES)
    assert all(v==0 for v in flat.curvature.values())
    assert all(math.isfinite(v) for v in curved.curvature.values())
    assert min(curved.curvature.values())<0<max(curved.curvature.values())
    assert all(curved.distance(p,q)>=flat.distance(p,q)-1e-12 for p,q in [((0,0),(10,10)),((5,5),(10,8))])


def test_adaptive_gate_uses_real_cell_and_verifier(monkeypatch):
    from omega_x_evolution import performance
    p=performance.Latency(100,120,150,192)
    monkeypatch.setattr(performance,'measure',lambda *a: ((p,)*3,(p,)*3))
    cfg=ClusterConfig(islands=2,rounds=2,batch=4,budget=16,topology=TopologyPolicy(split_count=2),policy=performance.Policy())
    old=initial_state(cfg,0);other=initial_state(cfg,1);actor=IslandActor(cfg,0)
    for i in range(2):
        migrant={'source':1,'revision':i+1,'artifact':other['elite']}
        new=actor.step(old,migrant,other['elite'])
        verify_transition(cfg,old,new,migrant,other['elite'],False)
        assert new['performance_records']
        old=new
    assert any(c['role']=='cell' for r in old['performance_records'] for c in r['comparisons'])
    forged=copy.deepcopy(new);forged['topology']['geometry_sha256']='0'*64
    with pytest.raises(ClusterError):verify_transition(cfg,initial_state(cfg,0),forged,None,other['elite'],False)


def test_geometry_cache_is_bounded():
    m=Manifold(TopologyPolicy(),CODES)
    for p in list(m.tensors)[:20]:m.distances(p)
    assert len(m._dist)<=16

def test_guided_mutation_is_parent_conditioned_and_valid():
    from omega_x_evolution.engine import apply_patch,Expression
    a=archive();p=a.lineage['0'];q=a.inspiration(p)
    assert q.id!=p.id
    patch=a.guided_patch(p,random.Random(7));code=apply_patch(p.code,patch)
    assert p.code in code and Expression(code)
    assert Cascade(42).evaluate(code).metrics[3]==1

def test_cli_topology_enabled_and_disabled(tmp_path):
    import subprocess,sys,json
    key=tmp_path/'key';key.write_bytes(b'k'*32)
    for flag in ([],['--topology']):
        db=tmp_path/('topo.db' if flag else 'fixed.db')
        p=subprocess.run([sys.executable,'-m','omega_x_evolution.cluster','--backend','simulation','--islands','1','--rounds','1','--batch','2','--budget','2','--parallelism','1','--db',str(db),'--key-file',str(key),*flag],capture_output=True,text=True,timeout=20)
        assert p.returncode==0,p.stderr
        assert ('topology' in json.loads(p.stdout))==bool(flag)
