import math
from itertools import product
import numpy as np
import pytest
from omega_x_evolution.ontos_continuous import advance, tick_count
from omega_x_evolution.ontos_repair import RepairState, inject, repair
from omega_x_evolution.ontos_logic import Poly, Lens, Heyting, Evidence, revise
from omega_x_evolution.ontos_testbed import replay


@pytest.mark.parametrize('surprise,ratio,expected', [(2,.2,1),(2,.5,4),(.7,.5,2),(.5,.5,1),(2,.45,2)])
def test_tick_bound(surprise,ratio,expected):
    assert tick_count(surprise,ratio)==expected


def test_continuous_scalar_reference_and_symmetry():
    state=(.1,-.2); obs=(.3,.4); seed=7; dt=.2
    out=advance(state,obs,dt,2.,.8,seed=seed)
    rng=np.random.default_rng(seed); scale=1/2
    f,g,h=[rng.normal(0,scale,(2,4)) for _ in range(3)]
    raw=np.abs(rng.normal(.35,.08,(2,2))); decay=(raw+raw.T)/2
    hist=[]; z=np.array(state)
    for _ in range(4):
        x=np.r_[z,obs]; gate=1/(1+np.exp(np.clip((f@x)*dt/4,-20,20)))
        z=gate*np.tanh(g@x)+(1-gate)*np.tanh(h@x); hist.append(z.copy())
    ref=[[sum(math.exp(-decay[i,j]*(3-k))*hist[k][i]*hist[k][j] for k in range(4))/sum(math.exp(-decay[i,j]*(3-k)) for k in range(4)) for j in range(2)] for i in range(2)]
    assert out.state==pytest.approx(z)
    assert np.array(out.sync)==pytest.approx(np.array(ref))
    assert out.sync[0][1]==out.sync[1][0]
    assert out==advance(state,obs,dt,2.,.8,seed=seed)


@pytest.mark.parametrize('state,obs,dt,seed', [((),(0.,),1.,7),((0.,),(float('nan'),),1.,7),((0.,),(0.,),0.,7),((0.,),(0.,),float('inf'),7),((0.,)*65,(0.,),1.,7),((0.,),(0.,),1.,True)])
def test_continuous_invalid(state,obs,dt,seed):
    with pytest.raises(ValueError): advance(state,obs,dt,1.,.8,seed=seed)


def test_repair_exact_contraction_and_atomic_debit():
    s=RepairState((0.,0.),1.,1000,1000)
    damaged=inject(s,(.4,-.3))
    nxt,r=repair(damaged,200)
    assert s.error==(0.,0.) and damaged.remaining==1000
    assert nxt.remaining==800 and r['spent']==200
    assert r['damage_before']==pytest.approx(.5)
    assert r['damage_after']==pytest.approx(.5*(1-.65*.2))
    assert r['closure']==pytest.approx(math.exp(-r['damage_after']))
    assert r['tame_temporal_proxy']==pytest.approx(1+9*r['closure']*.8)


def test_repair_exhausted_no_credit():
    s=RepairState((.5,),1.,100,10)
    nxt,r=repair(s,11)
    assert nxt==s and r['spent']==0 and r['damage_after']==r['damage_before']
    assert repair(s,1)[0]==s


@pytest.mark.parametrize('args', [((float('nan'),),1.,100,100),((0.,),1.1,100,100),((0.,),1.,100,101),((0.,),1.,True,0)])
def test_repair_invalid(args):
    with pytest.raises(ValueError): RepairState(*args)


def test_poly_lens_contravariant_composition():
    a=Poly((2,3)); b=Poly((2,)); c=Poly((1,))
    f=Lens(a,b,(0,0),((1,0),(2,1)))
    g=Lens(b,c,(0,),((1,),))
    assert f.compose(g)==Lens(a,c,(0,0),((0,),(1,)))
    assert Lens.identity(a).compose(f)==f==f.compose(Lens.identity(b))
    with pytest.raises(ValueError): g.compose(f)
    with pytest.raises(ValueError): Lens(a,b,(0,0),((2,0),(2,1)))


def test_poly_associativity_and_empty_fibers():
    a=Poly((2,)); b=Poly((1,)); c=Poly((1,)); d=Poly((0,))
    f=Lens(a,b,(0,),((1,),)); g=Lens(b,c,(0,),((0,),)); h=Lens(c,d,(0,),((),))
    assert f.compose(g).compose(h)==f.compose(g.compose(h))
    assert Lens.identity(d).compose(Lens.identity(d))==Lens.identity(d)


@pytest.mark.parametrize('opens', [(0,1,3),(0,1,2,3),(0,1,3,7)])
def test_heyting_exhaustive_adjunction_and_distributivity(opens):
    h=Heyting(opens); top=opens[-1]
    for a,b,c in product(opens,repeat=3):
        assert ((c&a)&~b==0)==(c&~h.implies(a,b)==0)
        assert a&(b|c)==(a&b)|(a&c)
    assert h.implies(top,0)==0
    if opens==(0,1,3): assert 1|h.implies(1,0)!=top


@pytest.mark.parametrize('opens', [(1,3),(0,1,2,7),(0,3,5,7),(0,1,1),(0,True)])
def test_invalid_topology(opens):
    with pytest.raises(ValueError): Heyting(opens)


def test_nars_provenance_conflict_and_no_evidence():
    a=Evidence('a',True,1); b=Evidence('b',False,1)
    assert revise(())['abstain']
    assert revise((a,b))==revise((b,a))
    r=revise((a,b)); assert r['frequency']==.5 and r['confidence']==pytest.approx(2/3) and r['conflict'] and r['abstain']
    assert revise((Evidence('c',True,10),))['frequency']==1
    with pytest.raises(ValueError): revise((a,a))
    with pytest.raises(ValueError): revise((a,Evidence('a',False,2)))


def test_offline_trace_integration():
    rows=replay(9274,(5,)*80); state=(0.,0.); s=RepairState((0.,0.),1.,100,100)
    for row in rows:
        state=advance(state,row.observation.continuous,.1,1.,s.remaining/s.budget,seed=7).state
        if row.observation.step==40: s=inject(s,(.5,.2))
        if row.observation.step==41: s,_=repair(s,10)
    assert all(abs(x)<=1 for x in state) and s.remaining==90
    assert revise((Evidence('trace-9274',True,1),))['confidence']==.5


def test_repair_dose_is_proportional_and_reserve_preserved():
    s=RepairState((.5,),1.,100,100)
    small,_=repair(s,1); large,_=repair(s,50)
    assert small.error[0]>large.error[0]
    assert small.error[0]==pytest.approx(.5*(1-.65/100))
    assert repair(s,86)[0]==s
    assert repair(s,85)[0].remaining==15


def test_all_three_point_topologies_have_heyting_adjunction():
    count=0
    for mask in range(64):
        opens=(0,)+tuple(i+1 for i in range(6) if mask>>i&1)+(7,)
        try: h=Heyting(opens)
        except ValueError: continue
        count+=1
        for a,b,c in product(opens,repeat=3):
            assert ((c&a)&~b==0)==(c&~h.implies(a,b)==0)
    assert count==29


def test_all_small_single_position_lenses_associate():
    for a,b,c,d in product(range(3),repeat=4):
        polys=[Poly((n,)) for n in (a,b,c,d)]
        def maps(p,q):
            return [Lens(p,q,(0,),(row,)) for row in product(range(p.fibers[0]),repeat=q.fibers[0])]
        for f,g,h in product(maps(*polys[:2]),maps(*polys[1:3]),maps(*polys[2:])):
            assert f.compose(g).compose(h)==f.compose(g.compose(h))


@pytest.mark.parametrize('ratio,alarm,damage,label', [(1.,False,0.,'HOMEOSTATIC'),(.29,False,0.,'SHOCK_REPAIR'),(1.,False,.36,'SHOCK_REPAIR'),(1.,True,0.,'IMMUNE_LOCKDOWN'),(.30,False,.35,'HOMEOSTATIC')])
def test_simulated_mode_is_only_a_label(ratio,alarm,damage,label):
    from omega_x_evolution.ontos_logic import simulated_mode
    assert simulated_mode(ratio,alarm,damage)==label


def test_simulated_mode_rejects_invalid_input():
    from omega_x_evolution.ontos_logic import simulated_mode
    with pytest.raises(ValueError): simulated_mode(1.,1,0.)
    with pytest.raises(ValueError): simulated_mode(float('nan'),False,0.)
