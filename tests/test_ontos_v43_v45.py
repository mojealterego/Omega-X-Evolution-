from itertools import product
import math
import pytest
from omega_x_evolution.ontos_signal_audit import audit
from omega_x_evolution.ontos_history import Fact, Snapshot, view, prototype_audit
from omega_x_evolution.ontos_metrics import assembly, causal_information


def test_offline_training_holdout_and_clocks():
    r=audit(42)
    assert r==audit(42)
    assert r['updates']==(64,16,4)
    assert r['train_mse']<r['frozen_train_mse']
    assert r['holdout_mse']<r['frozen_holdout_mse']
    assert r['retention_mse']<r['frozen_retention_mse']
    assert r['target_variance']>0 and not r['collapsed']
    assert 'weights' not in r


@pytest.mark.parametrize('seed',[-1,True,2**32,1.0])
def test_invalid_seed(seed):
    with pytest.raises(ValueError): audit(seed)


def fact(value, start, end, tx, source, tenant='a'):
    return Fact(tenant,'sensor','label',value,start,end,tx,source)


def test_bitemporal_history_late_correction_and_namespace():
    s=Snapshot((fact('old',0,100,1,'s1'),fact('new',20,40,3,'s2'),fact('other',0,100,1,'s1','b')))
    assert view(s,'a','sensor','label',30,2).value=='old'
    assert view(s,'a','sensor','label',30,3).value=='new'
    assert view(s,'a','sensor','label',40,3).value=='old'
    assert view(s,'b','sensor','label',30,3).value=='other'
    assert view(s,'c','sensor','label',30,3) is None
    assert view(s,'a','sensor','label',30,0) is None
    assert view(s,'a','sensor','label',30,3).source=='s2'


def test_conflict_duplicate_and_invalid_interval():
    a=fact('x',0,10,1,'s1')
    with pytest.raises(ValueError): Snapshot((a,a))
    with pytest.raises(ValueError): Snapshot((a,fact('y',5,15,1,'s2')))
    with pytest.raises(ValueError): fact('x',10,10,1,'s1')
    with pytest.raises(ValueError): view(Snapshot((a,)),'a','sensor','label',True,1)


def test_prototype_diagnostic_no_write_or_promotion():
    r=prototype_audit((1.,0.),((1.,0.),(0.,1.)),(.9,.1),max_noise=.2)
    assert not r['quarantined'] and r['energy_after']<=r['energy_before']+1e-12
    assert prototype_audit((1.,0.),((1.,0.),(0.,1.)),(-1.,0.),max_noise=.2)['quarantined']
    assert 'pattern' not in r
    with pytest.raises(ValueError): prototype_audit((0.,0.),((1.,0.),),(.9,.1),max_noise=.2)


@pytest.mark.parametrize('word,expected',[('a',0),('ab',1),('aaaa',2),('abababab',3),('abc',2),('ababa',3)])
def test_exact_assembly_known(word,expected):
    r=assembly(word)
    assert r['minimum']==expected and r['heuristic']>=expected


@pytest.mark.parametrize('word',['','abcdefghi','a b',None])
def test_assembly_invalid(word):
    with pytest.raises(ValueError): assembly(word)


def test_binary_assembly_exhaustive_bounds():
    for n in range(1,7):
        for letters in product('ab',repeat=n):
            r=assembly(''.join(letters))
            assert math.ceil(math.log2(n))<=r['minimum']<=r['heuristic']<=n-1


def test_identity_and_constant_causal_channels():
    a=causal_information(((1.,0.),(0.,1.)),((0,),(1,)))
    assert a['micro_ei_bits']==pytest.approx(1) and a['macro_ei_bits']==pytest.approx(1)
    b=causal_information(((1.,0.),(1.,0.)),((0,),(1,)))
    assert b['micro_ei_bits']==0 and b['macro_ei_bits']==0
    c=causal_information(((1.,0.),(0.,1.)),((0,1),))
    assert c['macro_ei_bits']==0 and c['delta_bits']==-1


def test_macro_causal_information_known_uneven_partition():
    g=((1.,0.,0.),(1.,0.,0.),(0.,0.,1.))
    r=causal_information(g,((0,1),(2,)))
    h=-(2/3)*math.log2(2/3)-(1/3)*math.log2(1/3)
    assert r['micro_ei_bits']==pytest.approx(h)
    assert r['macro_ei_bits']==pytest.approx(1)
    assert r['delta_bits']==pytest.approx(1-h)
    assert r['macro_cp']==pytest.approx(1)


@pytest.mark.parametrize('partition',[(),((0,),),((0,1),(1,)),((True,),(0,)),((0,),()),((0,),(2,))])
def test_invalid_partition(partition):
    with pytest.raises(ValueError): causal_information(((1.,0.),(0.,1.)),partition)


def test_assembly_independent_breadth_first_oracle():
    from collections import deque
    def oracle(word):
        initial=frozenset(word); queue=deque([(initial,0)]); seen={initial}
        while queue:
            available,cost=queue.popleft()
            if word in available: return cost
            for a,b in product(available,repeat=2):
                c=a+b
                if c not in available and c in word:
                    nxt=available|{c}
                    if nxt not in seen:
                        seen.add(nxt); queue.append((nxt,cost+1))
        raise AssertionError('unreachable target')
    for n in range(1,6):
        for letters in product('ab',repeat=n):
            word=''.join(letters)
            assert assembly(word)['minimum']==oracle(word)


@pytest.mark.parametrize('seed',[0,19,9274,2**32-1])
def test_signal_audit_other_seeds(seed):
    r=audit(seed)
    assert r==audit(seed) and r['holdout_mse']<r['frozen_holdout_mse']
    assert r['retention_mse']<r['frozen_retention_mse'] and not r['collapsed']


def test_history_order_independence():
    rows=(fact('x',0,10,1,'s1'),fact('y',2,5,2,'s2'),fact('z',3,8,3,'s3'))
    for t,q in product(range(11),range(5)):
        assert view(Snapshot(rows),'a','sensor','label',t,q)==view(Snapshot(rows[::-1]),'a','sensor','label',t,q)


def test_causal_metric_independent_kl_reference():
    g=((.4,.4,.2),(.1,.8,.1),(.2,.5,.3))
    ref=sum(p*math.log2(p/(sum(r[j] for r in g)/3))/3 for row in g for j,p in enumerate(row))
    result=causal_information(g,((0,),(1,),(2,)))
    assert result['micro_ei_bits']==pytest.approx(ref,abs=1e-14)
    assert result['macro_ei_bits']==pytest.approx(ref,abs=1e-14)


def test_vsa_fixed_noise_measurement():
    from omega_x_evolution.ontos_history import vsa_noise_audit
    a=(1,-1)*10; b=(-1,-1,1,1)*5
    assert vsa_noise_audit(a,b,())=={'bit_error_rate':0.,'cosine':1.}
    r=vsa_noise_audit(a,b,tuple(range(6)))
    assert r['bit_error_rate']==pytest.approx(.3) and r['cosine']==pytest.approx(.4)
    with pytest.raises(ValueError): vsa_noise_audit(a,b,(1,1))
    with pytest.raises(ValueError): vsa_noise_audit(a,b,(20,))
    with pytest.raises(ValueError): vsa_noise_audit((True,-1),(-1,1),())


def test_history_cap_and_touching_intervals():
    assert view(Snapshot((fact('x',0,10,1,'s1'),fact('y',10,20,1,'s2'))),'a','sensor','label',10,1).value=='y'
    with pytest.raises(ValueError): Snapshot(tuple(fact('x',0,10,t,'s1') for t in range(257)))
