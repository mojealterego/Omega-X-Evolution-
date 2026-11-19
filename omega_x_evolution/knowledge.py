"""Offline teacher-to-student distillation of operator routing probabilities.

Only training Cascade observations (not holdout) are used as soft labels.
Student is a small categorical conditional model, not an LLM or neural model.
"""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import math
import random
from .engine import BASELINE, VERSION, Cascade, Expression, apply_patch, score
from .meta import OPERATORS, Workflow, proposal_for

ROLES=('fast','deep')
PARENTS=(BASELINE,'-(x+y+abs(x-y))','-(x+y+(x-y)*(x-y))','-(x+y+abs(x-y)/(x+y+0.01))')
SCHEMA='omega-knowledge-v1'


def seeds(values):
    values=tuple(values)
    if not 1<=len(values)<=16 or any(type(s) is not int or not 0<=s<2**32 for s in values) or len(set(values))!=len(values):
        raise ValueError('invalid unique seed set')
    return values


def feature(role,parent):
    if role not in ROLES: raise ValueError('invalid role')
    return ROLES.index(role)*2+int(Expression(parent).operations>=5)


@dataclass(frozen=True)
class Example:
    seed:int
    index:int
    role:str
    parent:str
    rewards:tuple[float,...]

    def __post_init__(self):
        seeds((self.seed,)); feature(self.role,self.parent)
        if type(self.index) is not int or not 0<=self.index<64 or type(self.rewards) is not tuple or len(self.rewards)!=len(OPERATORS) or any(type(v) not in (int,float) or not 0<=v<=1 for v in self.rewards):
            raise ValueError('invalid teacher observation')


def soft(rewards):
    weights=[math.exp((v-max(rewards))/.08) for v in rewards]
    return tuple(w/sum(weights) for w in weights)


async def collect(seed_set, *, per_seed=12):
    seed_set=seeds(seed_set)
    if type(per_seed) is not int or not 1<=per_seed<=64: raise ValueError('record budget')
    output=[]
    for seed in sorted(seed_set):
        rng=random.Random(seed)
        for i in range(per_seed):
            role=ROLES[i%2]; parent=PARENTS[(i+seed)%len(PARENTS)]; proposal_seed=rng.randrange(2**32)
            prompt=json.dumps({'parent':parent}); rewards=[]
            for op in OPERATORS:
                patch=await proposal_for(Workflow((op,)))(role,prompt,proposal_seed)
                result=Cascade(seed).evaluate(apply_patch(parent,patch))
                rewards.append(score(result.metrics) if result.stage==3 and result.metrics[3]==1 else 0.)
            output.append(Example(seed,i,role,parent,tuple(rewards)))
    return tuple(output)


@dataclass(frozen=True)
class Student:
    train_seeds:tuple[int,...]
    rows:tuple[tuple[float,...],...]
    training_digest:str

    def __post_init__(self):
        if type(self.train_seeds) is not tuple or tuple(sorted(seeds(self.train_seeds)))!=self.train_seeds: raise ValueError('invalid training provenance')
        if type(self.rows) is not tuple or len(self.rows)!=4: raise ValueError('invalid model rows')
        for row in self.rows:
            if type(row) is not tuple or len(row)!=len(OPERATORS) or any(type(x) not in (int,float) or not 0<x<=1 for x in row) or not math.isclose(sum(row),1.,abs_tol=1e-12,rel_tol=0): raise ValueError('invalid probabilities')
        if not isinstance(self.training_digest,str) or len(self.training_digest)!=64 or any(c not in '0123456789abcdef' for c in self.training_digest): raise ValueError('invalid digest')

    def probabilities(self,role,parent): return self.rows[feature(role,parent)]

    def choose(self,role,parent):
        p=self.probabilities(role,parent)
        return max(range(len(p)),key=lambda i:(p[i],-i))

    def proposal(self):
        async def propose(role,prompt,seed):
            parent=json.loads(prompt)['parent']
            return await proposal_for(Workflow((OPERATORS[self.choose(role,parent)],)))(role,prompt,seed)
        return propose

    def to_json(self):
        return json.dumps({'schema':SCHEMA,'benchmark':VERSION,'operators':OPERATORS,'train_seeds':self.train_seeds,'rows':self.rows,'training_digest':self.training_digest},sort_keys=True,allow_nan=False,separators=(',',':'))

    @classmethod
    def from_json(cls,raw):
        if not isinstance(raw,str) or len(raw)>32768: raise ValueError('invalid model size')
        try:
            v=json.loads(raw)
            if set(v)!={'schema','benchmark','operators','train_seeds','rows','training_digest'} or v['schema']!=SCHEMA or v['benchmark']!=VERSION or tuple(v['operators'])!=OPERATORS: raise ValueError('invalid model contract')
            return cls(tuple(v['train_seeds']),tuple(tuple(r) for r in v['rows']),v['training_digest'])
        except (KeyError,TypeError,RecursionError) as exc: raise ValueError('invalid model contract') from exc


def fit(data):
    data=tuple(data)
    if not 1<=len(data)<=1024 or any(not isinstance(x,Example) for x in data) or len({(x.seed,x.index) for x in data})!=len(data): raise ValueError('invalid training records')
    data=sorted(data,key=lambda x:(x.seed,x.index))
    train=tuple(sorted({x.seed for x in data})); seeds(train)
    sums=[[1.]*len(OPERATORS) for _ in range(4)]
    for x in data:
        row=sums[feature(x.role,x.parent)]
        for i,p in enumerate(soft(x.rewards)): row[i]+=p
    rows=tuple(tuple(v/sum(row) for v in row) for row in sums)
    digest=hashlib.sha256(json.dumps([(x.seed,x.index,x.role,x.parent,x.rewards) for x in data],separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return Student(train,rows,digest)


async def experiment(train_seeds=(21,22,23), validation_seeds=(31,32), *, per_seed=12):
    train_seeds=seeds(train_seeds); validation_seeds=seeds(validation_seeds)
    if set(train_seeds)&set(validation_seeds): raise ValueError('training/validation overlap')
    train=await collect(train_seeds,per_seed=per_seed); student=fit(train)
    validation=await collect(validation_seeds,per_seed=per_seed)
    chosen=[x.rewards[student.choose(x.role,x.parent)] for x in validation]
    teacher=[max(x.rewards) for x in validation]
    n=len(validation)
    return {'train_seeds':list(train_seeds),'validation_seeds':list(validation_seeds),'training_records':len(train),'validation_records':n,'student_calls':n,'teacher_calls':n*len(OPERATORS),'teacher_mean':sum(teacher)/n,'student_mean':sum(chosen)/n,'mean_regret':sum(t-c for t,c in zip(teacher,chosen))/n,'top1_accuracy':sum(t==c for t,c in zip(teacher,chosen))/n,'model':json.loads(student.to_json())}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--records-per-seed',type=int,default=12); a=p.parse_args()
    print(json.dumps(asyncio.run(experiment(per_seed=a.records_per_seed)),indent=2,allow_nan=False))


if __name__=='__main__': main()
