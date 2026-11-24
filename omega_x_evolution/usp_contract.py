"""USP five-view diagnostic scorer for bounded intent-slot and IE frames.

Reference: Li et al., Xing USP, arXiv:2610.34343v1, §3.7, §4.1, Tab. 4.

This module scores *already produced* frames. It never interprets a frame as an
executable tool request, makes model calls, repairs labels, or grants authority.
Matching is exact and deterministic. Output equivalence is a multiset equality.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
from typing import Any, Sequence

MAX_SCHEMA_CATEGORIES = 64
MAX_CATEGORY_ARGS = 32
MAX_INSTANCES_PER_CATEGORY = 32
MAX_TOTAL_INSTANCES = 256
MAX_NAME_CHARS = 128
MAX_VALUE_CHARS = 1024
MAX_INPUT_BYTES = 2_097_152
MAX_RECORDS = 10_000
VIEWS = ('category', 'field', 'field_value', 'instance_bound', 'complete_instance')
FAMILIES = ('NER', 'RE', 'EE', 'Intent-slot')

# None is an internal sentinel, distinct from a literal string 'NO_VALUE'.
Atom = tuple[str | None, str | None]
Instance = tuple[str, tuple[Atom, ...]]


def _distinct(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if key in result:
            raise ValueError('duplicate JSON object key')
        result[key] = val
    return result


def _json(data: str) -> Any:
    if type(data) is not str or len(data.encode('utf-8')) > MAX_INPUT_BYTES:
        raise ValueError('JSON size bound')
    def bad_constant(_: str) -> None:
        raise ValueError('invalid JSON numeric constant')
    try:
        return json.loads(data, object_pairs_hook=_distinct, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError('invalid JSON payload') from exc


def _name(value: Any) -> str:
    if (type(value) is not str or not value or len(value) > MAX_NAME_CHARS
            or value != value.strip() or any(ord(c) < 32 for c in value)):
        raise ValueError('invalid USP name')
    return value


def _read_schema(raw: Any) -> dict[str, frozenset[str]]:
    if (type(raw) is not list or not 1 <= len(raw) <= MAX_SCHEMA_CATEGORIES):
        raise ValueError('schema bounds')
    allowed: dict[str, frozenset[str]] = {}
    for entry in raw:
        if type(entry) is not dict or not {'category', 'args'} <= entry.keys() or not entry.keys() <= {'category', 'category_description', 'args'}:
            raise ValueError('invalid schema category')
        cat = _name(entry['category'])
        if cat in allowed:
            raise ValueError('duplicate category name')
        if 'category_description' in entry and (type(entry['category_description']) is not str or len(entry['category_description']) > 4096):
            raise ValueError('invalid category description')
        fields = entry['args']
        if type(fields) is not list or len(fields)>MAX_CATEGORY_ARGS:
            raise ValueError('invalid field list')
        names: set[str] = set()
        for field in fields:
            if type(field) is not dict or 'name' not in field or not field.keys() <= {'name', 'description'}:
                raise ValueError('invalid field descriptor')
            name = _name(field['name'])
            if name in names:
                raise ValueError('duplicate field name')
            if 'description' in field and (type(field['description']) is not str or len(field['description']) > 4096):
                raise ValueError('invalid field description')
            names.add(name)
        allowed[cat]=frozenset(names)
    return allowed


def _instances(data: Any, schema: dict[str, frozenset[str]]) -> tuple[tuple[str, ...], tuple[Instance, ...]]:
    if type(data) is not list or len(data)>MAX_SCHEMA_CATEGORIES:
        raise ValueError('USP category list bound')
    categories: set[str]=set()
    instances: list[Instance]=[]
    per_cat: Counter[str]=Counter()
    for entry in data:
        if type(entry) is not dict or set(entry) != {'category', 'args'}:
            raise ValueError('USP category object must contain category and args')
        cat = _name(entry['category'])
        if cat not in schema:
            raise ValueError('category outside schema')
        categories.add(cat)
        groups=entry['args']
        if type(groups) is not list:
            raise ValueError('invalid instance groups')
        per_cat[cat]+=len(groups)
        if per_cat[cat]>MAX_INSTANCES_PER_CATEGORY or len(instances)+len(groups)>MAX_TOTAL_INSTANCES:
            raise ValueError('instance budget')
        for group in groups:
            if type(group) is not dict or len(group)>MAX_CATEGORY_ARGS:
                raise ValueError('invalid instance fields')
            fields: list[Atom]=[]
            for field,value in group.items():
                if _name(field) not in schema[cat]:
                    raise ValueError('unknown field')
                if type(value) is not str or len(value)>MAX_VALUE_CHARS or any(ord(c)<32 and c not in '\n\t' for c in value):
                    raise ValueError('invalid field value')
                fields.append((field, value if value else None))
            instances.append((cat,tuple(sorted(fields, key=lambda x: x[0]))))
    return tuple(sorted(categories)),tuple(instances)


def _sets(categories: tuple[str, ...], instances: tuple[Instance, ...]) -> dict[str, set[tuple]]:
    field: set[tuple]=set()
    value: set[tuple]=set()
    for cat,groups in instances:
        for name,val in (groups or ((None,None),)):
            field.add((cat,name))
            value.add((cat,name,val))
    # Includes categories explicitly selected with no serialized instance group.
    for cat in categories:
        if not any(c==cat for c,_ in instances):
            field.add((cat,None));value.add((cat,None,None))
    return {'category':{(cat,) for cat in categories}, 'field':field, 'field_value':value}


def score_counts(tp: int, fp: int, fn: int) -> dict[str, int|float]:
    if any(type(x) is not int or x<0 for x in (tp,fp,fn)):
        raise ValueError('nonnegative integer counts required')
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0.0
    return {'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':f1}


def _counts(pred: set[tuple], gold: set[tuple]) -> dict[str,int|float]:
    tp=len(pred & gold)
    return score_counts(tp,len(pred)-tp,len(gold)-tp)


def _maximum_weight(weights: list[list[int]]) -> int:
    """Deterministic exact O(k^3) Hungarian assignment, padding to square."""
    m=len(weights)
    n=max(m,max((len(row) for row in weights),default=0))
    if n==0:return 0
    if n>MAX_INSTANCES_PER_CATEGORY:
        raise ValueError('assignment budget')
    pad=[row+[0]*(n-len(row)) for row in weights]+[[0]*n for _ in range(n-m)]
    if any(w<0 or type(w) is not int for row in pad for w in row):
        raise ValueError('nonnegative integer edge weight')
    largest=max((max(row) for row in pad),default=0)
    cost=[[largest-w for w in row] for row in pad]
    u=[0]*(n+1);v=[0]*(n+1);p=[0]*(n+1);way=[0]*(n+1)
    for i in range(1,n+1):
        p[0]=i
        j0=0
        minv=[math.inf]*(n+1)
        used=[False]*(n+1)
        while True:
            used[j0]=True
            i0=p[j0]
            delta=math.inf;j1=0
            for j in range(1,n+1):
                if used[j]:continue
                cur=cost[i0-1][j-1]-u[i0]-v[j]
                if cur<minv[j]: minv[j]=cur;way[j]=j0
                if minv[j]<delta:delta=minv[j];j1=j
            for j in range(n+1):
                if used[j]:u[p[j]]+=int(delta);v[j]-=int(delta)
                else:minv[j]-=delta
            j0=j1
            if p[j0]==0:break
        while True:
            j1=way[j0]
            p[j0]=p[j1]
            j0=j1
            if not j0:break
    return sum(pad[p[j]-1][j-1] for j in range(1,n+1) if p[j]>0)


def _instance_bound(pred:tuple[Instance,...],gold:tuple[Instance,...]) -> dict[str,int|float]:
    groups_p: dict[str,list[set[Atom]]]=defaultdict(list)
    groups_g: dict[str,list[set[Atom]]]=defaultdict(list)
    for cat,fields in pred:groups_p[cat].append(set(fields or ((None,None),)))
    for cat,fields in gold:groups_g[cat].append(set(fields or ((None,None),)))
    total_p=sum(len(x) for group in groups_p.values() for x in group)
    total_g=sum(len(x) for group in groups_g.values() for x in group)
    matched=0
    for cat in sorted(groups_p.keys() | groups_g.keys()):
        pp=groups_p[cat];gg=groups_g[cat]
        matched+=_maximum_weight([[len(x & y) for y in gg] for x in pp])
    return score_counts(matched,total_p-matched,total_g-matched)


def evaluate(prediction: Any, reference: Any, schema: Any) -> dict[str,Any]:
    """Score one prediction with five views and strict multiset equality.

    Bad reference/schema raises ValueError; invalid model output is an empty
    prediction with parsed=False, not an exception or a successful empty output.
    """
    valid_schema=_read_schema(_json(schema) if type(schema) is str else schema)
    try:
        gc,gi=_instances(_json(reference) if type(reference) is str else reference,valid_schema)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError('invalid gold reference') from exc
    parsed=True
    try:
        pc,pi=_instances(_json(prediction) if type(prediction) is str else prediction,valid_schema)
    except (ValueError, TypeError, UnicodeError):
        parsed=False;pc=();pi=()
    pred_atoms=_sets(pc,pi);gold_atoms=_sets(gc,gi)
    scores={name:_counts(pred_atoms[name],gold_atoms[name]) for name in VIEWS[:3]}
    scores['instance_bound']=_instance_bound(pi,gi)
    scores['complete_instance']=_multiset_counts(pi,gi)
    return {'parsed':parsed,'equality_accuracy':int(parsed and pc==gc and Counter(pi)==Counter(gi)),
            'views':scores,'promotion_authorized':False}


def _multiset_counts(pred:tuple[Instance,...], gold:tuple[Instance,...]) -> dict[str,int|float]:
    p=Counter(pred);g=Counter(gold)
    tp=sum((p & g).values())
    return score_counts(tp,sum(p.values())-tp,sum(g.values())-tp)


def aggregate(records: Sequence[dict[str,Any]], schema: Any) -> dict[str,Any]:
    """Dataset-micro, family-macro, equally weighted nonempty family-macro."""
    valid_schema=_read_schema(_json(schema) if type(schema) is str else schema)
    if type(records) not in (tuple,list) or not 1<=len(records)<=MAX_RECORDS:
        raise ValueError('records count')
    by_data:dict[tuple[str,str],dict[str,Any]]={}
    ids:set[str]=set()
    for item in records:
        if type(item) is not dict or set(item)!={'id','family','dataset','gold','prediction'}:
            raise ValueError('record must have exact keys')
        ident=_name(item['id']);family=item['family'];dataset=_name(item['dataset'])
        if ident in ids or family not in FAMILIES:
            raise ValueError('duplicate id or unknown task family')
        ids.add(ident)
        r=evaluate(item['prediction'],item['gold'],valid_schema_to_raw(valid_schema))
        bucket=by_data.setdefault((family,dataset), {'views':{v:[0,0,0] for v in VIEWS},
                                                    'count':0,'parse':0,'eq':0})
        bucket['count']+=1
        bucket['parse']+=int(r['parsed'])
        bucket['eq']+=r['equality_accuracy']
        for v in VIEWS:
            for i,key in enumerate(('tp','fp','fn')):
                bucket['views'][v][i]+=r['views'][v][key]
    dataset_results={}
    family_results:dict[str,list[dict[str,float]]]=defaultdict(list)
    for (family,dataset),batch in sorted(by_data.items()):
        result={v:score_counts(*batch['views'][v])['f1'] for v in VIEWS}
        result['parse_success']=batch['parse']/batch['count']
        result['equality_accuracy']=batch['eq']/batch['count']
        dataset_results[f'{family}/{dataset}']=result
        family_results[family].append(result)
    family_scores={f:{metric:sum(r[metric] for r in rows)/len(rows)
                      for metric in (*VIEWS,'parse_success','equality_accuracy')}
                   for f,rows in sorted(family_results.items())}
    return {'sample_count':len(records),'dataset_count':len(dataset_results),
            'family_scores':family_scores,
            'overall':{v:sum(vals[v] for vals in family_scores.values())/len(family_scores)
                       for v in (*VIEWS,'parse_success','equality_accuracy')},
            'datasets':dataset_results,
            'promotion_authorized':False}


def valid_schema_to_raw(schema: dict[str,frozenset[str]]) -> list[dict[str,Any]]:
    return [{'category':k,'args':[{'name':v} for v in sorted(fields)]}
            for k,fields in sorted(schema.items())]


def read_jsonl(path:Path) -> list[dict[str,Any]]:
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_INPUT_BYTES:
        raise ValueError('JSONL file bound')
    try: content=path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:raise ValueError('JSONL decoding error') from exc
    lines=content.splitlines()
    if not 1<=len(lines)<=MAX_RECORDS or any(not line.strip() for line in lines):
        raise ValueError('JSONL record count/empty line')
    return [_json(line) for line in lines]


def run_cli(argv:Sequence[str]|None=None) -> int:
    ap=argparse.ArgumentParser(description='Bounded USP five-view evaluator (no tool execution).')
    ap.add_argument('--schema',required=True,type=Path)
    ap.add_argument('--records',required=True,type=Path)
    args=ap.parse_args(argv)
    if not args.schema.is_file() or args.schema.stat().st_size>MAX_INPUT_BYTES:
        raise ValueError('schema file bound')
    result=aggregate(read_jsonl(args.records), _json(args.schema.read_text(encoding='utf-8')))
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')))
    return 0


if __name__=='__main__':
    raise SystemExit(run_cli())
