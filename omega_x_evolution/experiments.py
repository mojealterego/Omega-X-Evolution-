"""Automatic construction of bounded, reproducible numeric experiments.

Plan generation cannot observe final test labels. Only a selected candidate
is evaluated on test. No executable plans, external tools or arbitrary code.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .compute import Router, CPUBackend, probe
from .discovery import Dataset, discover
from .formal import verified_optimize
from .graph_memory import GraphMemory, canonical
from .neural import Architecture, fit, digest, rmse
from .neuro_symbolic import Split, fixture, symbolic_predictions

NEURAL=Architecture((8,), 'tanh','momentum',.05)
RESIDUAL=Architecture((16,16),'tanh','momentum',.05)
CANDIDATES=('symbolic','neural','hybrid')
MAX_WORK=200_000_000


def _digest(obj): return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _data_contract(data):
    return _digest({'train':[asdict(x) for x in data.train], 'validation':[asdict(x) for x in data.validation]})


@dataclass(frozen=True)
class Plan:
    data_contract: str
    seed: int
    budget: int
    epochs: int
    work_cap: int
    candidates: tuple[str,...]

    def __post_init__(self):
        if type(self.data_contract) is not str or len(self.data_contract)!=64 or any(c not in '0123456789abcdef' for c in self.data_contract): raise ValueError('invalid data contract')
        if (any(type(x) is not int for x in (self.seed,self.budget,self.epochs,self.work_cap)) or
            not 0<=self.seed<2**32 or not 1<=self.budget<=4096 or not 1<=self.epochs<=400 or not 1<=self.work_cap<=MAX_WORK): raise ValueError('invalid experiment bounds')
        if type(self.candidates) is not tuple or self.candidates not in (CANDIDATES[:1],CANDIDATES[:2],CANDIDATES): raise ValueError('invalid experiment candidates')

    def to_json(self): return canonical({'schema':'omega-experiment-plan-v1',**asdict(self)})

    @classmethod
    def from_json(cls, raw):
        if type(raw) is not str or len(raw)>16384: raise ValueError('plan size')
        try:
            v=json.loads(raw)
            if v.pop('schema')!='omega-experiment-plan-v1' or type(v['candidates']) is not list: raise ValueError('plan schema')
            v['candidates']=tuple(v['candidates']);return cls(**v)
        except (TypeError,KeyError,AttributeError,RecursionError) as exc: raise ValueError('plan schema') from exc


def design(data:Split, *, seed=42,budget=128,epochs=100,work_cap=MAX_WORK):
    if not isinstance(data,Split): raise ValueError('invalid dataset')
    base=Plan(_data_contract(data),seed,budget,epochs,work_cap,('symbolic',))
    if budget*len(data.train)>1_000_000: raise ValueError('symbolic work cap')
    # Fixed policy: admit neural fit and then residual fit only when their
    # combined epoch*sample*parameter proxy fits the declared training budget.
    unit=len(data.train)*epochs
    count=1+int(unit*NEURAL.parameters<=work_cap)+int(unit*(NEURAL.parameters+RESIDUAL.parameters)<=work_cap)
    return Plan(base.data_contract,seed,budget,epochs,work_cap,CANDIDATES[:count])


def execute(plan:Plan,data:Split, *, router:Router|None=None,memory:GraphMemory|None=None):
    if not isinstance(plan,Plan) or not isinstance(data,Split): raise ValueError('invalid experiment')
    # Reject altered/over-budget plans and changed train or validation inputs.
    if plan!=design(data,seed=plan.seed,budget=plan.budget,epochs=plan.epochs,work_cap=plan.work_cap): raise ValueError('plan contract mismatch')
    if router is None: router=Router([CPUBackend()])
    if not isinstance(router,Router) or (memory is not None and not isinstance(memory,GraphMemory)): raise ValueError('invalid execution services')
    routing=[]; models={}; validation={}; work=0
    report=discover(Dataset(data.train,data.validation),seed=plan.seed,budget=plan.budget)
    expression=verified_optimize(report['expression']).source
    validation['symbolic']=report['holdout_rmse']
    try: sym_val=symbolic_predictions(expression,data.validation)
    except (ArithmeticError,ValueError): sym_val=None
    def infer(name,model,rows,split):
        r=router.infer(model,rows)
        routing.append({'candidate':name,'split':split,'device':r.device,'physical':r.physical,'attempts':list(r.attempts),'failures':[list(f) for f in r.failures]})
        return r.values
    for name in plan.candidates[1:]:
        arch=NEURAL if name=='neural' else RESIDUAL
        residual=symbolic_predictions(expression,data.train) if name=='hybrid' else None
        model=fit(arch,data.train,seed=plan.seed,epochs=plan.epochs,residual=residual)
        models[name]=model;work+=plan.epochs*len(data.train)*arch.parameters
        pred=infer(name,model,data.validation,'validation')
        validation[name]=(None if sym_val is None else rmse(pred+sym_val,data.validation)) if name=='hybrid' else rmse(pred,data.validation)
    valid=[name for name in plan.candidates if validation[name] is not None]
    if not valid: raise RuntimeError('no valid candidate on validation')
    selected=min(valid,key=lambda name:(validation[name],0 if name=='symbolic' else models[name].architecture.parameters,CANDIDATES.index(name)))
    # All selection is complete before the final test is read.
    try:
        if selected=='symbolic': pred=symbolic_predictions(expression,data.test)
        else:
            pred=infer(selected,models[selected],data.test,'test')
            if selected=='hybrid': pred=pred+symbolic_predictions(expression,data.test)
        test_rmse=rmse(pred,data.test)
    except (ArithmeticError,ValueError): test_rmse=None
    result={'schema':'omega-experiment-result-v1','plan':json.loads(plan.to_json()),'plan_sha256':_digest(json.loads(plan.to_json())),
            'dataset_sha256':data.digest(),'expression':expression,'validation':validation,'selected':selected,
            'test_rmse':test_rmse,'attempts':report['attempts'],'validation_evaluations':len(plan.candidates),'test_evaluations':1,
            'training_work':work,'routing':routing,'model':json.loads(models[selected].to_json()) if selected!='symbolic' else None,
            'weights_sha256':digest(models[selected]) if selected!='symbolic' else None}
    if memory is not None:
        plan_id,result_id=memory.record_experiment(result['plan'],result)
        result.update(plan_id=plan_id,result_id=result_id)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--task',choices=('smooth','xor'),default='smooth');p.add_argument('--dataset',type=Path);p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int,default=128);p.add_argument('--epochs',type=int,default=100);p.add_argument('--work-cap',type=int,default=MAX_WORK);p.add_argument('--torch',action='store_true');p.add_argument('--npu',action='store_true');p.add_argument('--db',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--tenant',default='research');p.add_argument('--plan-only',action='store_true');a=p.parse_args()
    if bool(a.db)!=bool(a.key_file): p.error('db and key-file required together')
    if a.dataset:
        with a.dataset.open(encoding='utf-8') as f: data=Split.from_json(f.read(262145))
    else: data=fixture(a.task,seed=a.seed)
    plan=design(data,seed=a.seed,budget=a.budget,epochs=a.epochs,work_cap=a.work_cap)
    if a.plan_only: print(plan.to_json());return
    memory=None
    if a.db:
        with a.key_file.open('rb') as f: key=f.read(4097)
        memory=GraphMemory(a.db,key,a.tenant)
    print(json.dumps(execute(plan,data,router=Router(probe(enable_torch=a.torch,enable_npu=a.npu)),memory=memory),indent=2,allow_nan=False))


if __name__=='__main__': main()
