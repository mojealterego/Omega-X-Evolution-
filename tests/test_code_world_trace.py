"""CWM-inspired exact u16 expression execution-trace verification."""
from __future__ import annotations

import copy
import hashlib
import json
import random

import pytest

from omega_x_evolution.polyglot import Program, evaluate
from omega_x_evolution.code_world_trace import trace_program, verify_prediction, score_predictions


def program(tree=('add', ('x',), ('y',))):
    return Program(tree)


def observed(tree=('add', ('x',), ('y',)), x=4, y=7):
    p = program(tree)
    return p, trace_program(p, x, y)


def test_postorder_full_trace_contract():
    p, result = observed(('mul', ('add', ('x',), ('lit', 3)), ('sub', ('y',), ('lit', 2))), 5, 7)
    assert result['schema'] == 'omega-cwm-u16-trace-v1'
    assert result['steps'] == [
        {'path':'LL', 'op':'x', 'value':5},
        {'path':'LR', 'op':'lit', 'value':3},
        {'path':'L', 'op':'add', 'value':8},
        {'path':'RL', 'op':'y', 'value':7},
        {'path':'RR', 'op':'lit', 'value':2},
        {'path':'R', 'op':'sub', 'value':5},
        {'path':'', 'op':'mul', 'value':40},
    ]
    assert result['output'] == 40
    assert result['program_sha256'] == hashlib.sha256(json.dumps(p.tree,separators=(',',':')).encode()).hexdigest()
    assert verify_prediction(p, 5, 7, result)['status'] == 'TRACE_MATCH_FINITE'


@pytest.mark.parametrize('tree,x,y,expected',[
    (('x',), 65535, 0, 65535),
    (('y',), 65535, 0, 0),
    (('lit', 65535), 0, 1, 65535),
    (('add',('x',),('lit',1)), 65535, 0, 0),
    (('sub',('x',),('lit',1)), 0, 0, 65535),
    (('mul',('x',),('y',)), 65535, 65535, 1),
    (('xor',('x',),('y',)), 0xAAAA, 0xFFFF, 0x5555),
    (('and',('x',),('y',)), 0xAAAA, 0x0F0F, 0x0A0A),
    (('or',('x',),('y',)), 0xAAAA, 0x0F0F, 0xAFAF),
])
def test_all_operations_have_exact_u16_semantics(tree,x,y,expected):
    p, trace = observed(tree,x,y)
    assert trace['output'] == evaluate(p,x,y) == expected
    assert verify_prediction(p,x,y,trace)['release_authorized'] is False


@pytest.mark.parametrize('tamper,value',[
    ('output', 12), ('x', 5), ('y', 10), ('schema', 'other'),
    ('program_sha256', '0'*64), ('steps', []),
])
def test_field_tampering_is_never_accepted(tamper,value):
    p, trace = observed()
    tampered = copy.deepcopy(trace); tampered[tamper] = value
    verdict=verify_prediction(p, 4, 7, tampered)
    assert verdict['status'] != 'TRACE_MATCH_FINITE'
    assert verdict['release_authorized'] is False


def test_value_mismatch_reports_position_and_no_approval():
    p, trace = observed()
    trace['steps'][0]['value'] = 9
    v = verify_prediction(p,4,7,trace)
    assert v['status']=='TRACE_MISMATCH'
    assert v['first_mismatch_step']==0
    assert v['matched_prefix_steps']==0
    assert not v['release_authorized']


def test_only_final_output_mismatch_uses_special_index():
    p, trace = observed()
    trace['output']=6
    v=verify_prediction(p,4,7,trace)
    assert v['status']=='TRACE_MISMATCH'
    assert v['first_mismatch_step']==3
    assert v['matched_prefix_steps']==3


def test_step_reordering_is_not_ignored():
    p,trace=observed()
    trace['steps'][0],trace['steps'][1]=trace['steps'][1],trace['steps'][0]
    v=verify_prediction(p,4,7,trace)
    assert v['status']=='TRACE_MISMATCH' and v['first_mismatch_step']==0


@pytest.mark.parametrize('edit',[
    lambda a: a.update(extra=True),
    lambda a: a.update(output=True),
    lambda a: a['steps'][0].update(value=True),
    lambda a: a['steps'][0].update(path='LLLLLLLLL'),
    lambda a: a['steps'][0].update(op='__import__'),
    lambda a: a['steps'][0].update(injected='evil'),
    lambda a: a.update(steps='invalid'),
    lambda a: a.update(steps=[0]),
    lambda a: a.update(program_sha256='deadbeef'),
])
def test_malformed_predictions_fail_closed(edit):
    p,trace=observed()
    edit(trace)
    v=verify_prediction(p,4,7,trace)
    assert v['status']=='TRACE_INVALID'
    assert not v['release_authorized']


@pytest.mark.parametrize('raw',[
    '{', '{"schema":1}',
    '{"x":2,"x":3}',
    '{"x":NaN}',
    '{"x":Infinity}',
    '"opaque"',
    '[]',
])
def test_invalid_json_predictions_are_rejected(raw):
    p=program()
    assert verify_prediction(p,4,7,raw)['status']=='TRACE_INVALID'


def test_json_round_trip_is_supported():
    p,trace=observed()
    assert verify_prediction(p,4,7,json.dumps(trace))['status']=='TRACE_MATCH_FINITE'


def test_oversized_prediction_rejected_without_parse():
    p=program()
    assert verify_prediction(p,4,7,'{'+' '*40000+'}')['status']=='TRACE_INVALID'


@pytest.mark.parametrize('x,y',[(True,0),(0,False),(-1,1),(65536,1),(1,1.1),('2',3)])
def test_invalid_coordinates_throw_before_trace_generation(x,y):
    with pytest.raises(ValueError): trace_program(program(),x,y)


def test_revalidated_program_rejects_object_mutation():
    p=program()
    object.__setattr__(p,'tree',('add',('x',),('unknown',)))
    with pytest.raises(ValueError): trace_program(p,1,2)


def test_batch_failure_inclusive_and_unapproved():
    p, t=observed()
    wrong=copy.deepcopy(t);wrong['output']+=1
    result=score_predictions(((p,4,7,t),(p,4,7,wrong),(p,4,7,None)))
    assert result=={'schema':'omega-cwm-u16-batch-v1','total':3,'matched':1,'mismatched':1,'invalid':1,'accuracy':pytest.approx(1/3),'release_authorized':False}


def test_batch_rejects_empty_or_over_budget():
    p,t=observed()
    for cases in [(), ((p,4,7,t),)*129, [1], ((p,4,7,t,5),), ((p,4,7,t),('bad',4,7,t))]:
        with pytest.raises(ValueError): score_predictions(cases)


def test_program_binding_prevents_mutate_fix_forgery():
    p,t=observed(('add',('x',),('y',)),4,7)
    mutated=program(('sub',('x',),('y',)))
    v=verify_prediction(mutated,4,7,t)
    assert v['status']=='TRACE_MISMATCH'
    assert not v['release_authorized']


def _independent(tree,x,y):
    op=tree[0]
    if op=='x':return x
    if op=='y':return y
    if op=='lit':return tree[1]
    a=_independent(tree[1],x,y)
    b=_independent(tree[2],x,y)
    return {'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,
            'xor':lambda:a^b,'and':lambda:a&b,'or':lambda:a|b}[op]() % 65536


def _random_tree(rng,depth=0):
    if depth>=5 or rng.random()<0.3:
        v=rng.choice(['x','y','lit'])
        return (v,) if v!='lit' else ('lit',rng.randrange(65536))
    return (rng.choice(['add','sub','mul','xor','and','or']),_random_tree(rng,depth+1),_random_tree(rng,depth+1))


def test_randomized_differential_semantics_replay_seed_20261124():
    rng=random.Random(20261124)
    checked=0
    for i in range(600):
        tree=_random_tree(rng)
        p=program(tree)
        x,y=rng.randrange(65536),rng.randrange(65536)
        trace=trace_program(p,x,y)
        assert trace['output']==_independent(tree,x,y)==evaluate(p,x,y)
        assert len(trace['steps'])==p.size
        assert verify_prediction(p,x,y,trace)['status']=='TRACE_MATCH_FINITE'
        checked+=1
    assert checked==600


def test_concurrent_independent_trace_requests_are_idempotent():
    from concurrent.futures import ThreadPoolExecutor
    p=program(('xor',('add',('x',),('y',)),('lit',65535)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        observed=list(pool.map(lambda n:trace_program(p,n,n+1),range(128)))
    assert len(observed)==128
    assert all(a['output']==((n+n+1)^65535)&65535 for n,a in enumerate(observed))
    assert all(verify_prediction(p,n,n+1,a)['status']=='TRACE_MATCH_FINITE' for n,a in enumerate(observed))


def test_cli_outputs_exact_trace_and_validates_model_prediction(tmp_path):
    import subprocess
    import os
    import sys
    args=[sys.executable,'-m','omega_x_evolution.code_world_trace',
          '--program','["add",["x"],["y"]]','--x','4','--y','7']
    env={**os.environ,'PYTHONPATH':'.'}
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    generated=subprocess.run(args, cwd=root,env=env,text=True,capture_output=True,timeout=10)
    assert generated.returncode==0,generated.stderr
    trace=json.loads(generated.stdout)
    assert trace['output']==11
    valid=tmp_path/'trace.json'
    valid.write_text(json.dumps(trace),encoding='utf-8')
    checked=subprocess.run(args+['--prediction-file',str(valid)], cwd=root,env=env,
                           text=True,capture_output=True,timeout=10)
    assert checked.returncode==0,checked.stderr
    assert json.loads(checked.stdout)['status']=='TRACE_MATCH_FINITE'
    trace['steps'][-1]['value']=4
    valid.write_text(json.dumps(trace),encoding='utf-8')
    denied=subprocess.run(args+['--prediction-file',str(valid)],cwd=root,env=env,
                          text=True,capture_output=True,timeout=10)
    assert denied.returncode==2
    assert json.loads(denied.stdout)['status']=='TRACE_MISMATCH'


def test_cli_rejects_code_execution_payload_without_side_effect(tmp_path):
    import subprocess
    import os
    import sys
    sentinel=tmp_path/'should_not_exist'
    injected=f'__import__("pathlib").Path("{sentinel}").write_text("oops")'
    root=__import__('pathlib').Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,'-m','omega_x_evolution.code_world_trace',
                           '--program',injected,'--x','0','--y','0'],
                          cwd=root,env={**os.environ,'PYTHONPATH':'.'},
                          text=True,capture_output=True,timeout=10)
    assert result.returncode!=0
    assert not sentinel.exists()


def test_prediction_json_nested_duplicate_step_key_rejected():
    p,t=observed()
    raw=json.dumps(t)
    raw=raw.replace('"path": "L",', '"path": "L", "path": "R",',1)
    assert verify_prediction(p,4,7,raw)['status']=='TRACE_INVALID'


def test_verdict_always_denies_release_even_on_maximal_valid_program():
    tree=('x',)
    for n in range(8):
        tree=('add',tree,('lit',n))
    p,t=observed(tree,65535,0)
    v=verify_prediction(p,65535,0,t)
    assert v['status']=='TRACE_MATCH_FINITE'
    assert v['release_authorized'] is False
    assert len(t['steps'])==17


def test_batch_is_deterministic_under_reordering_and_missing_predictions():
    p=program(('xor',('x',),('y',)))
    a=trace_program(p,1,2)
    b=trace_program(p,2,4)
    b['output']^=1
    cases=((p,1,2,a),(p,2,4,b),(p,3,5,None))
    direct=score_predictions(cases)
    reversed_order=score_predictions(cases[::-1])
    assert direct==reversed_order


def test_nested_json_prediction_extreme_budget_rejected():
    p=program()
    assert verify_prediction(p,1,1,'['*1000+']'*1000)['status']=='TRACE_INVALID'


def test_nested_ir_conversion_caps_depth_even_before_program_validation():
    from omega_x_evolution.code_world_trace import _nested_tuple
    raw=['x']
    for _ in range(10):
        raw=['add',raw,['lit',1]]
    with pytest.raises(ValueError):
        _nested_tuple(raw)


def test_main_in_process_generates_and_rechecks_exact_trace(monkeypatch,capsys,tmp_path):
    import sys
    from omega_x_evolution.code_world_trace import main
    args=['program','--program','["xor",["x"],["y"]]','--x','10','--y','5']
    monkeypatch.setattr(sys,'argv',args)
    assert main()==0
    result=json.loads(capsys.readouterr().out)
    assert result['output']==15
    path=tmp_path/'pred.json'
    path.write_text(json.dumps(result),encoding='utf-8')
    monkeypatch.setattr(sys,'argv',args+['--prediction-file',str(path)])
    assert main()==0
    verdict=json.loads(capsys.readouterr().out)
    assert verdict['status']=='TRACE_MATCH_FINITE'
    result['steps'][-1]['value']=0
    path.write_text(json.dumps(result),encoding='utf-8')
    assert main()==2
    assert json.loads(capsys.readouterr().out)['status']=='TRACE_MISMATCH'


@pytest.mark.parametrize('data,expect',[
    (b'\0', 'invalid'),
    (b'{' + b' '*32769 + b'}','prediction file budget exceeded'),
])
def test_main_fails_closed_for_invalid_prediction_file(tmp_path,monkeypatch,capsys,data,expect):
    import sys
    from omega_x_evolution.code_world_trace import main
    path=tmp_path/'untrusted.json'
    path.write_bytes(data)
    monkeypatch.setattr(sys,'argv',['program','--program','["x"]','--x','1','--y','0','--prediction-file',str(path)])
    if expect=='prediction file budget exceeded':
        with pytest.raises(SystemExit) as ex: main()
        assert ex.value.code==2
        assert expect in capsys.readouterr().err
    else:
        assert main()==2
        assert json.loads(capsys.readouterr().out)['status']=='TRACE_INVALID'


def test_main_rejects_oversized_source_before_parse(monkeypatch,capsys):
    import sys
    from omega_x_evolution.code_world_trace import main
    monkeypatch.setattr(sys,'argv',['program','--program','["x"]'+' '*8193,'--x','1','--y','0'])
    with pytest.raises(SystemExit) as ex: main()
    assert ex.value.code==2
    assert 'IR JSON budget exceeded' in capsys.readouterr().err
