"""USP five-view semantic extraction/intent-slot evaluator (arXiv:2610.34343v1)."""
from __future__ import annotations

import json
import math
import random
import pytest

from omega_x_evolution.usp_contract import (evaluate, aggregate, score_counts,
                                             read_jsonl, run_cli)

SCHEMA = [
    {"category": "ToolCall", "args": [{"name": "tool"}, {"name": "target"}]},
    {"category": "GetWeather", "args": [{"name": "state"}]},
    {"category": "NoAction", "args": []},
]


def frame(category="ToolCall", *groups):
    return [{"category": category, "args": list(groups)}]


def score(gold, pred, *, schema=SCHEMA):
    return evaluate(pred, gold, schema)


def test_identical_full_instance_match():
    r = score(frame('ToolCall', {'tool':'read','target':'a'}), frame('ToolCall', {'tool':'read','target':'a'}))
    assert r['parsed'] is True and r['equality_accuracy'] == 1
    assert all(s['f1'] == 1.0 for s in r['views'].values())


def test_wrong_binding_category_and_field_value_do_not_expose_error():
    gold=frame('ToolCall',{'tool':'read','target':'a'},{'tool':'write','target':'b'})
    pred=frame('ToolCall',{'tool':'read','target':'b'},{'tool':'write','target':'a'})
    r=score(gold,pred)
    assert r['views']['category']['f1'] == 1.
    assert r['views']['field']['f1'] == 1.
    assert r['views']['field_value']['f1'] == 1.
    assert r['views']['instance_bound']['tp'] == 2
    assert r['views']['instance_bound']['f1'] == 0.5
    assert r['views']['complete_instance']['f1'] == 0.0
    assert r['equality_accuracy'] == 0


def test_duplicate_instances_preserved_only_in_instance_aware_views():
    gold=frame('GetWeather', {'state':'GA'}, {'state':'GA'})
    pred=frame('GetWeather', {'state':'GA'})
    r=score(gold,pred)
    assert r['views']['category']['f1'] == 1.
    assert r['views']['field_value']['f1'] == 1.
    assert (r['views']['complete_instance']['tp'],r['views']['complete_instance']['fn']) == (1,1)
    assert r['views']['complete_instance']['f1'] == pytest.approx(2/3)


def test_more_predicted_instances_penalized():
    r=score(frame('GetWeather',{'state':'CA'}),frame('GetWeather',{'state':'CA'},{'state':'CA'}))
    assert r['views']['complete_instance']['fp'] == 1


def test_unordered_instances_equal():
    a=frame('GetWeather',{'state':'GA'},{'state':'CA'})
    b=frame('GetWeather',{'state':'CA'},{'state':'GA'})
    assert score(a,b)['equality_accuracy'] == 1


def test_fields_are_not_synthesized_if_omitted():
    r=score(frame('ToolCall',{'tool':'read','target':'a'}),frame('ToolCall',{'tool':'read'}))
    assert r['views']['field']['fn'] == 1
    assert r['views']['field_value']['fn'] == 1


def test_empty_value_is_distinct_from_missing_field():
    r=score(frame('GetWeather',{'state':''}),frame('GetWeather',{}))
    assert r['views']['field_value']['tp'] == 0
    assert r['views']['field_value']['fn'] == 1
    assert r['equality_accuracy'] == 0


def test_missing_field_with_a_literal_no_value_is_not_silent_match():
    r=score(frame('GetWeather',{'state':''}),frame('GetWeather',{'state':'NO_VALUE'}))
    assert r['views']['field_value']['tp'] == 0


def test_no_arg_category_special_matching_atom():
    r=score([{'category':'NoAction','args':[{}]}],[{'category':'NoAction','args':[{}]}])
    assert all(s['f1'] == 1 for s in r['views'].values())


def test_empty_arg_list_describes_category_with_no_instance():
    r=score([{'category':'NoAction','args':[]}],[{'category':'NoAction','args':[]}])
    assert r['views']['category']['f1']==1.
    assert r['views']['complete_instance']['tp']==0


def test_empty_pred_ref_f1_zero_but_equality_one():
    r=score([],[])
    assert not any(s['f1'] for s in r['views'].values())
    assert r['equality_accuracy'] == 1 and r['parsed']


@pytest.mark.parametrize('invalid', ['{', '[] trailing', 'null', '{}', '{"category":"X"}',
     '[{"category":"NoAction","args":[{}],"args":[]}]',
     '[{"category":"NotInSchema","args":[]}]',
     '[{"category":"ToolCall","args":[{"irrelevant":"a"}]}]',
     '[{"category":"GetWeather","args":[{"state":null}]}]',
     '[{"category":"GetWeather","args":[{"state":NaN}]}]',
     35, None, '', '\ud800'])
def test_bad_predictions_fail_closed_and_score_as_empty(invalid):
    r=score(frame('GetWeather',{'state':'GA'}),invalid)
    assert r['parsed'] is False
    assert r['views']['category']['tp']==0
    assert r['views']['category']['fn']==1
    assert r['equality_accuracy']==0


def test_invalid_gold_never_silently_excluded():
    with pytest.raises(ValueError):score('[{"category":"Wrong","args":[]}]',[])


@pytest.mark.parametrize('invalid_schema', [[], {}, [{"category":"A", "args":[{"name":"x"},{"name":"x"}]}],
        [{"category":"A", "args":[]},{"category":"A", "args":[]}],
        [{"category":"A", "args": "x"}],
        [{"category":"A", "args":[],"executable":True}]])
def test_invalid_schema_rejected(invalid_schema):
    with pytest.raises(ValueError):score([], [],schema=invalid_schema)


def test_field_names_not_collapsed_into_value_string():
    ref=frame('ToolCall',{'tool':'a|b','target':'c'})
    pred=frame('ToolCall',{'tool':'a','target':'b|c'})
    assert score(ref,pred)['views']['complete_instance']['tp']==0


def test_large_predictions_are_failed_closed():
    r=score(frame('GetWeather',{'state':'GA'}), '[' + ' '*2_100_000 + ']')
    assert not r['parsed']


def test_instance_matching_is_global_optimum_not_greedy():
    # g0 can match p0 with 2 overlaps, p1 with 1; g1 can only match p0.
    # Greedy (g0,p0) yields 2; optimal (g0,p1)+(g1,p0) yields 3.
    schema=[{'category':'C','args':[{'name':name} for name in ['a','b','c','d']]}]
    gold=frame('C',{'a':'1','b':'2'}, {'c':'3','d':'4'})
    pred=frame('C',{'a':'1','b':'2','c':'3'}, {'a':'1','b':'2'})
    r=score(gold,pred,schema=schema)
    assert r['views']['instance_bound']['tp']==3


def test_prediction_json_string_and_python_records_equivalent():
    ref=frame('GetWeather',{'state':'GA'})
    assert score(ref,ref)==score(ref,json.dumps(ref))


def test_json_cannot_smuggle_duplicate_keys_in_group():
    pred='[{"category":"GetWeather","args":[{"state":"GA","state":"CA"}]}]'
    assert not score(frame('GetWeather',{'state':'GA'}),pred)['parsed']


def test_bounded_random_permutation_invariance():
    seed=521
    rng=random.Random(seed)
    for n in range(1,14):
        values=[{'state':f's{i}'} for i in range(n)]
        a=frame('GetWeather',*values)
        rng.shuffle(values)
        b=frame('GetWeather',*values)
        r=score(a,b)
        assert r['equality_accuracy']==1
        assert r['views']['instance_bound']['tp']==n

@pytest.mark.parametrize('values',[(1,0,0),(0,1,1),(0,0,0)])
def test_zero_denominator_f1_and_counts(values):
    tp,fp,fn=values
    s=score_counts(tp,fp,fn)
    assert math.isfinite(s['f1']) and 0 <= s['f1'] <= 1


def test_dataset_balanced_not_naive_global_micro():
    # One dataset with a match and another with a miss: equal weight.
    records=[
       {'id':'1','family':'NER','dataset':'A', 'gold':frame('GetWeather',{'state':'GA'}), 'prediction':frame('GetWeather',{'state':'GA'})},
       {'id':'2','family':'NER','dataset':'B', 'gold':frame('GetWeather',{'state':'GA'}), 'prediction':[]},
       {'id':'3','family':'Intent-slot','dataset':'C', 'gold':frame('GetWeather',{'state':'GA'}), 'prediction':frame('GetWeather',{'state':'GA'})},
    ]
    result=aggregate(records,SCHEMA)
    assert result['family_scores']['NER']['field_value']==pytest.approx(.5)
    assert result['overall']['field_value']==pytest.approx(.75)
    assert result['sample_count']==3


def test_parse_failed_with_empty_gold_not_equal():
    r=score([],None)
    assert not r['parsed'] and not r['equality_accuracy']


def test_aggregate_rejects_unmatched_duplicate_ids():
    row={'id':'x','family':'NER','dataset':'A','gold':[],'prediction':[]}
    with pytest.raises(ValueError):aggregate([row,row],SCHEMA)


def test_reject_nan_in_input_schema():
    with pytest.raises(ValueError):score([],[],schema=[{'category':'A','args':[{'name':'x','description':float('nan')}]}])


def test_cli_jsonl_end_to_end(tmp_path,capsys):
    schema=tmp_path/'schema.json';inp=tmp_path/'results.jsonl'
    schema.write_text(json.dumps(SCHEMA))
    inp.write_text(json.dumps({'id':'x','family':'NER','dataset':'A',
     'gold':frame('GetWeather',{'state':'GA'}), 'prediction':frame('GetWeather',{'state':'GA'})})+'\n')
    assert run_cli(['--schema',str(schema),'--records',str(inp)])==0
    out=json.loads(capsys.readouterr().out)
    assert out['overall']['complete_instance']==1


def test_cli_rejects_trailing_file_data(tmp_path):
    p=tmp_path/'bad.jsonl';p.write_text('{}\n'+'x'*2_200_000)
    with pytest.raises(ValueError):read_jsonl(p)


def test_assignment_matches_independent_exhaustive_oracle():
    import itertools
    from omega_x_evolution.usp_contract import _maximum_weight
    rng=random.Random(271828)
    for n in range(1,6):
        for _ in range(60):
            mat=[[rng.randrange(0,6) for _ in range(n)] for _ in range(n)]
            reference=max(sum(mat[i][perm[i]] for i in range(n))
                          for perm in itertools.permutations(range(n)))
            assert _maximum_weight(mat)==reference


def test_assignment_rectangular_against_independent_oracle():
    import itertools
    from omega_x_evolution.usp_contract import _maximum_weight
    rng=random.Random(141421)
    for rows in range(1,5):
        for cols in range(1,5):
            for _ in range(15):
                mat=[[rng.randrange(0,4) for _ in range(cols)] for _ in range(rows)]
                n=max(rows,cols)
                padded=[row+[0]*(n-cols) for row in mat]+[[0]*n for _ in range(n-rows)]
                reference=max(sum(padded[i][perm[i]] for i in range(n))
                              for perm in itertools.permutations(range(n)))
                assert _maximum_weight(mat)==reference


def test_views_are_not_monotonic_pass_rates():
    r=score(frame('ToolCall',{'tool':'read','target':'a'},{'tool':'write','target':'b'}),
            frame('ToolCall',{'tool':'read','target':'b'},{'tool':'write','target':'a'}))
    assert r['views']['field_value']['f1']>r['views']['instance_bound']['f1']
    assert r['promotion_authorized'] is False


def test_aggregate_invalid_gold_triggers_failure():
    records=[{'id':'x','family':'NER','dataset':'A','gold':frame('Unknown',{}),'prediction':[]}]
    with pytest.raises(ValueError):aggregate(records,SCHEMA)


def test_reject_values_over_bound():
    r=score(frame('GetWeather',{'state':'GA'}),frame('GetWeather',{'state':'x'*1025}))
    assert r['parsed'] is False


def test_equal_repeated_instances_from_separate_category_objects():
    gold=[{'category':'GetWeather','args':[{'state':'GA'}]},
          {'category':'GetWeather','args':[{'state':'CA'}]}]
    pred=frame('GetWeather',{'state':'CA'},{'state':'GA'})
    assert score(gold,pred)['equality_accuracy']==1
