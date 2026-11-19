"""Opt-in isolated Torch training, verified against native NumPy training.

Process isolation prevents Torch/OpenMP state from contaminating fork workers.
Accelerator availability is checked in the child. No implicit backend fallback.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
import math
import os
import subprocess
import sys

import numpy as np

from .neural import Architecture, Model, fit as reference_fit, predict, _array
from .discovery import Observation

TARGETS=('cpu','cuda','mps','npu')


class Trainer:
    def __init__(self,device='cpu', *,timeout=60):
        if device not in TARGETS or type(timeout) is not int or not 1<=timeout<=300: raise ValueError('invalid training device or timeout')
        self.device=device;self.timeout=timeout

    def fit(self,architecture,rows, *,seed=42,epochs=200,residual=None):
        # Validate configuration and compute the unchanged reference oracle first.
        ref=reference_fit(architecture,rows,seed=seed,epochs=epochs,residual=residual)
        payload={'architecture':asdict(architecture),'rows':[asdict(p) for p in rows],'seed':seed,'epochs':epochs,'device':self.device,'residual':None if residual is None else residual.tolist()}
        raw=json.dumps(payload,allow_nan=False,separators=(',',':'))
        # Child imports Torch only; do not pass API credentials to it.
        allowed=('PATH','HOME','TMPDIR','TEMP','TMP','SYSTEMROOT','WINDIR','LD_LIBRARY_PATH','DYLD_LIBRARY_PATH','ASCEND_HOME_PATH','ASCEND_OPP_PATH','CUDA_VISIBLE_DEVICES','PYTHONPATH')
        env={**{k:os.environ[k] for k in allowed if k in os.environ},'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
        try:
            r=subprocess.run([sys.executable,'-m','omega_x_evolution.training','--worker'],input=raw,text=True,capture_output=True,timeout=self.timeout,env=env,check=True)
        except subprocess.CalledProcessError as exc: raise RuntimeError(f'Torch training failed on {self.device}') from exc
        except subprocess.TimeoutExpired as exc: raise RuntimeError('Torch training timeout') from exc
        model=Model.from_json(r.stdout)
        if model.architecture!=ref.architecture or model.scale!=ref.scale or len(model.losses)!=len(ref.losses): raise RuntimeError('training contract mismatch')
        if not np.allclose(predict(model,rows),predict(ref,rows),rtol=1e-5,atol=1e-7) or not np.allclose(model.losses,ref.losses,rtol=1e-5,atol=1e-7): raise RuntimeError('training reference mismatch')
        return model


def _worker(raw):
    import torch
    torch.set_num_threads(1)
    if len(raw)>262144: raise ValueError('worker input size')
    v=json.loads(raw); device=v['device'];a=v['architecture'];a['hidden']=tuple(a['hidden']); arch=Architecture(**a)
    rows=tuple(Observation(**r) for r in v['rows']);x,y=_array(rows);seed=v['seed'];epochs=v['epochs']
    if device not in TARGETS or type(seed) is not int or not 0<=seed<2**32 or type(epochs) is not int or not 1<=epochs<=2000 or epochs*len(rows)*arch.parameters>200_000_000: raise ValueError('worker bounds')
    if device=='cuda' and not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
    if device=='mps' and not torch.backends.mps.is_available(): raise RuntimeError('MPS unavailable')
    if device=='npu':
        import torch_npu  # noqa: F401 - operator-installed extension
        if not torch.npu.is_available(): raise RuntimeError('NPU unavailable')
    dtype=torch.float32 if device in ('npu','mps') else torch.float64
    if v['residual'] is not None:
        residual=np.asarray(v['residual'],dtype=np.float64)
        if residual.shape!=y.shape or not np.isfinite(residual).all() or np.max(np.abs(residual))>1e12:raise ValueError('invalid residual')
        y=y-residual
    scale=float(max(1.,np.max(np.abs(y))));y=y/scale
    rng=np.random.default_rng(seed);shapes=(2,*arch.hidden,1)
    w=[torch.tensor(rng.uniform(-math.sqrt(6/(a+b)),math.sqrt(6/(a+b)),size=(a,b)),device=device,dtype=dtype,requires_grad=True) for a,b in zip(shapes,shapes[1:])]
    b=[torch.zeros((1,n),device=device,dtype=dtype,requires_grad=True) for n in shapes[1:]]
    xx=torch.tensor(x,device=device,dtype=dtype); yy=torch.tensor(y,device=device,dtype=dtype)
    params=w+b;velocity=[torch.zeros_like(p) for p in params];beta=.9 if arch.optimizer=='momentum' else 0.;losses=[]
    for step in range(epochs+1):
        out=xx
        for i,(ww,bb) in enumerate(zip(w,b)):
            out=out@ww+bb
            if i<len(w)-1:out=torch.tanh(out) if arch.activation=='tanh' else torch.relu(out)
        loss=torch.mean((out-yy)**2); val=float(loss.detach().cpu().item())
        if not math.isfinite(val):raise RuntimeError('nonfinite training loss')
        losses.append(val)
        if step==epochs:break
        loss.backward()
        with torch.no_grad():
            for i,p in enumerate(params):
                velocity[i]=beta*velocity[i]+p.grad.clamp(-5,5);p.sub_(arch.learning_rate*velocity[i]);p.grad=None
    convert=lambda vs:tuple(p.detach().cpu().numpy().astype(np.float64) for p in vs)
    return Model(arch,convert(w),convert(b),scale,tuple(losses))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker',action='store_true');p.add_argument('--device',choices=TARGETS,default='cpu');p.add_argument('--epochs',type=int,default=25);p.add_argument('--seed',type=int,default=42);a=p.parse_args()
    if a.worker:print(_worker(sys.stdin.read(262145)).to_json());return
    from .neural import BASELINE
    from .neuro_symbolic import fixture
    d=fixture('smooth',seed=a.seed); model=Trainer(a.device).fit(BASELINE,d.train,seed=a.seed,epochs=a.epochs)
    print(json.dumps({'device':a.device,'reference_verified':True,'loss_before':model.losses[0],'loss_after':model.losses[-1],'model':json.loads(model.to_json())},indent=2,allow_nan=False))


if __name__=='__main__':main()
