"""Bounded neural architecture and optimizer evolution using real NumPy training."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random
import numpy as np

WIDTHS = (4, 8, 16, 32)
ACTIVATIONS = ('tanh', 'relu')
OPTIMIZERS = ('sgd', 'momentum')
RATES = (.02, .05, .08)


@dataclass(frozen=True)
class Architecture:
    hidden: tuple[int, ...]
    activation: str
    optimizer: str
    learning_rate: float

    def __post_init__(self):
        if (type(self.hidden) is not tuple or not 1<=len(self.hidden)<=3 or
            any(type(v) is not int or v not in WIDTHS for v in self.hidden) or
            self.activation not in ACTIVATIONS or self.optimizer not in OPTIMIZERS or
            type(self.learning_rate) is not float or self.learning_rate not in RATES):
            raise ValueError('invalid architecture')

    @property
    def parameters(self):
        shape=(2,*self.hidden,1)
        return sum((a+1)*b for a,b in zip(shape,shape[1:]))

    def mutate(self, rng):
        h=list(self.hidden); action=rng.randrange(6)
        if action==0: h[rng.randrange(len(h))]=rng.choice(WIDTHS)
        elif action==1 and len(h)<3: h.insert(rng.randrange(len(h)+1),rng.choice(WIDTHS))
        elif action==2 and len(h)>1: h.pop(rng.randrange(len(h)))
        elif action==3: return Architecture(self.hidden,rng.choice(ACTIVATIONS),self.optimizer,self.learning_rate)
        elif action==4: return Architecture(self.hidden,self.activation,rng.choice(OPTIMIZERS),self.learning_rate)
        else: return Architecture(self.hidden,self.activation,self.optimizer,rng.choice(RATES))
        return Architecture(tuple(h),self.activation,self.optimizer,self.learning_rate)


BASELINE=Architecture((4,),'tanh','sgd',.05)


@dataclass(frozen=True)
class Model:
    architecture: Architecture
    weights: tuple[np.ndarray,...]
    biases: tuple[np.ndarray,...]
    scale: float
    losses: tuple[float,...]

    def to_json(self):
        return json.dumps({'schema':'omega-mlp-v1','architecture':asdict(self.architecture),'weights':[v.tolist() for v in self.weights],'biases':[v.tolist() for v in self.biases],'scale':self.scale,'losses':self.losses},sort_keys=True,allow_nan=False,separators=(',',':'))

    @classmethod
    def from_json(cls,raw):
        if not isinstance(raw,str) or len(raw)>262144: raise ValueError('model size')
        try:
            v=json.loads(raw)
            if set(v)!= {'schema','architecture','weights','biases','scale','losses'} or v['schema']!='omega-mlp-v1': raise ValueError('model schema')
            a=dict(v['architecture']);a['hidden']=tuple(a['hidden']);arch=Architecture(**a)
            def tensor(rows):
                if type(rows) is not list or any(type(row) is not list or any(type(n) not in (int,float) for n in row) for row in rows): raise ValueError('invalid tensor values')
                return np.array(rows,dtype=np.float64)
            if type(v['scale']) not in (int,float): raise ValueError('invalid scale')
            return cls(arch,tuple(tensor(w) for w in v['weights']),tuple(tensor(b) for b in v['biases']),float(v['scale']),tuple(v['losses']))
        except (TypeError,KeyError,OverflowError,RecursionError) as exc: raise ValueError('model shape') from exc

    def __post_init__(self):
        if not isinstance(self.architecture,Architecture): raise ValueError('invalid model architecture')
        shapes=(2,*self.architecture.hidden,1)
        if type(self.weights) is not tuple or type(self.biases) is not tuple or len(self.weights)!=len(shapes)-1 or len(self.biases)!=len(self.weights): raise ValueError('invalid model layers')
        if type(self.scale) is not float or not 1<=self.scale<=2e12: raise ValueError('invalid scale')
        for w,b,i,j in zip(self.weights,self.biases,shapes,shapes[1:]):
            if not isinstance(w,np.ndarray) or not isinstance(b,np.ndarray) or w.dtype!=np.float64 or b.dtype!=np.float64 or w.shape!=(i,j) or b.shape!=(1,j) or not np.isfinite(w).all() or not np.isfinite(b).all(): raise ValueError('invalid model tensors')
            w.setflags(write=False); b.setflags(write=False)
        if type(self.losses) is not tuple or not 1<=len(self.losses)<=2001 or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in self.losses): raise ValueError('invalid losses')


def _array(rows):
    from .discovery import Observation
    if type(rows) is not tuple or not 1<=len(rows)<=512 or any(not isinstance(p,Observation) for p in rows): raise ValueError('invalid neural observations')
    return np.array([(p.x,p.y) for p in rows],dtype=np.float64)*2-1, np.array([p.z for p in rows],dtype=np.float64).reshape(-1,1)


def _forward(a, weights, biases, activation):
    layers=[a]
    for i,(w,b) in enumerate(zip(weights,biases)):
        z=layers[-1]@w+b
        if i<len(weights)-1: z=np.tanh(z) if activation=='tanh' else np.maximum(z,0)
        layers.append(z)
    return layers


def fit(architecture: Architecture, rows, *, seed=42, epochs=200, residual=None):
    """Full-batch backpropagation, deterministic initialization, bounded work."""
    if not isinstance(architecture,Architecture) or type(seed) is not int or not 0<=seed<2**32 or type(epochs) is not int or not 1<=epochs<=2000:
        raise ValueError('invalid training configuration')
    x,y=_array(rows)
    if residual is not None:
        if not isinstance(residual,np.ndarray) or residual.shape!=y.shape or not np.isfinite(residual).all() or np.max(np.abs(residual))>1e12: raise ValueError('invalid symbolic predictions')
        y=y-residual
    if epochs*len(rows)*architecture.parameters>200_000_000: raise ValueError('training operation budget')
    scale=float(max(1.,np.max(np.abs(y)))); y=y/scale
    rng=np.random.default_rng(seed); shapes=(2,*architecture.hidden,1)
    w=[rng.uniform(-math.sqrt(6/(a+b)),math.sqrt(6/(a+b)),size=(a,b)) for a,b in zip(shapes,shapes[1:])]
    b=[np.zeros((1,d)) for d in shapes[1:]]; vw=[np.zeros_like(v) for v in w]; vb=[np.zeros_like(v) for v in b]
    losses=[]; beta=.9 if architecture.optimizer=='momentum' else 0.; rate=architecture.learning_rate
    for step in range(epochs+1):
        layers=_forward(x,w,b,architecture.activation); err=layers[-1]-y
        loss=float(np.mean(err**2))
        if not math.isfinite(loss): raise RuntimeError('nonfinite training loss')
        losses.append(loss)
        if step==epochs: break
        delta=2*err/len(rows); dw=[]; db=[]
        for i in range(len(w)-1,-1,-1):
            dw.append(layers[i].T@delta); db.append(delta.sum(axis=0,keepdims=True))
            if i:
                deriv=1-layers[i]**2 if architecture.activation=='tanh' else (layers[i]>0)
                delta=(delta@w[i].T)*deriv
        for i,(gw,gb) in enumerate(zip(reversed(dw),reversed(db))):
            vw[i]=beta*vw[i]+np.clip(gw,-5,5); vb[i]=beta*vb[i]+np.clip(gb,-5,5)
            w[i]-=rate*vw[i]; b[i]-=rate*vb[i]
    return Model(architecture,tuple(w),tuple(b),scale,tuple(losses))


def predict(model: Model, rows):
    if not isinstance(model,Model): raise ValueError('invalid model')
    x,_=_array(rows)
    values=_forward(x,model.weights,model.biases,model.architecture.activation)[-1]*model.scale
    if not np.isfinite(values).all(): raise RuntimeError('nonfinite predictions')
    return values


def rmse(values, rows):
    _,y=_array(rows)
    if values.shape!=y.shape or not np.isfinite(values).all(): raise ValueError('invalid predictions')
    return float(np.sqrt(np.mean((values-y)**2)))


def digest(model):
    h=hashlib.sha256(json.dumps(asdict(model.architecture),sort_keys=True).encode());h.update(np.asarray([model.scale],dtype='<f8').tobytes())
    for p in (*model.weights,*model.biases): h.update(p.astype('<f8').tobytes())
    return h.hexdigest()


def evolve_architectures(data, *, rounds=3,population=4,epochs=180,seed=42):
    from .neuro_symbolic import Split
    if not isinstance(data,Split) or any(type(v) is not int for v in (rounds,population,epochs,seed)) or not 1<=rounds<=10 or not 2<=population<=12 or not 1<=epochs<=2000 or not 0<=seed<2**32: raise ValueError('architecture search budget')
    cap=rounds*population*epochs*len(data.train)*Architecture((32,32,32),'tanh','sgd',.05).parameters
    if cap>500_000_000: raise ValueError('total training budget')
    rng=random.Random(seed); pool=[BASELINE,Architecture((8,8),'tanh','momentum',.05)]
    while len(pool)<population: pool.append(BASELINE.mutate(rng))
    cache={}; history=[]
    for i in range(rounds):
        for a in pool:
            if a in cache: continue
            model=fit(a,data.train,seed=seed,epochs=epochs); val=rmse(predict(model,data.validation),data.validation)
            cache[a]=(val,model)
            history.append({'round':i,'architecture':asdict(a),'parameters':a.parameters,'validation_rmse':val,'initial_loss':model.losses[0],'final_loss':model.losses[-1],'weights_sha256':digest(model)})
        winner=min(cache,key=lambda a:(cache[a][0],a.parameters,a.hidden,a.activation,a.optimizer,a.learning_rate))
        pool=[winner]+[winner.mutate(rng) for _ in range(population-1)]
    baseline=cache[BASELINE]; selected=cache[winner]
    # Test labels enter only after all architecture choices are committed.
    return {'schema':'omega-nas-v1','dataset_sha256':data.digest(),'seed':seed,'rounds':rounds,'population':population,'epochs':epochs,'history':history,'training_runs':len(cache),'training_run_bound':rounds*population,'training_work_bound':cap,
            'baseline':asdict(BASELINE),'selected':asdict(winner),'baseline_parameters':BASELINE.parameters,'selected_parameters':winner.parameters,
            'baseline_validation_rmse':baseline[0],'selected_validation_rmse':selected[0],
            'baseline_test_rmse':rmse(predict(baseline[1],data.test),data.test),'selected_test_rmse':rmse(predict(selected[1],data.test),data.test),
            'selected_weights_sha256':digest(selected[1]),'model':json.loads(selected[1].to_json())}


def main():
    from .neuro_symbolic import fixture, Split
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--rounds',type=int,default=3);p.add_argument('--population',type=int,default=4);p.add_argument('--epochs',type=int,default=180);p.add_argument('--task',choices=('smooth','xor'),default='xor');p.add_argument('--dataset',type=Path);a=p.parse_args()
    if a.dataset:
        with a.dataset.open(encoding='utf-8') as f: data=Split.from_json(f.read(262145))
    else: data=fixture(a.task,seed=a.seed)
    print(json.dumps(evolve_architectures(data,seed=a.seed,rounds=a.rounds,population=a.population,epochs=a.epochs),indent=2,allow_nan=False))


if __name__=='__main__': main()
