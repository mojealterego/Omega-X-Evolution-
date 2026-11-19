"""Fixed cloud job workload; accelerators are required, never simulated silently."""
from __future__ import annotations
import argparse
import asyncio
import json
import math
import os


def _jax_train(rows,*,seed,epochs,platform):
    import jax
    import jax.numpy as jnp
    import numpy as np
    from .neural import BASELINE,Model,_array,fit,predict
    if platform not in ('cpu','tpu'):raise ValueError('JAX platform')
    devices=jax.devices(platform)
    if not devices or devices[0].platform!=platform:raise RuntimeError('requested JAX device unavailable')
    device=devices[0];arch=BASELINE;reference=fit(arch,rows,seed=seed,epochs=epochs)
    x,y=_array(rows);scale=float(max(1.,np.max(np.abs(y))));y=y/scale;rng=np.random.default_rng(seed);shapes=(2,*arch.hidden,1)
    put=lambda v:jax.device_put(np.asarray(v,dtype=np.float32),device)
    params=(tuple(put(rng.uniform(-math.sqrt(6/(a+b)),math.sqrt(6/(a+b)),size=(a,b))) for a,b in zip(shapes,shapes[1:])),tuple(put(np.zeros((1,d))) for d in shapes[1:]));xx=put(x);yy=put(y)
    def loss(p):
        z=xx
        for i,(w,b) in enumerate(zip(*p)):
            z=z@w+b
            if i<len(p[0])-1:z=jnp.tanh(z)
        return jnp.mean((z-yy)**2)
    @jax.jit
    def step(p):
        value,grad=jax.value_and_grad(loss)(p)
        return value,jax.tree_util.tree_map(lambda a,b:a-arch.learning_rate*jnp.clip(b,-5,5),p,grad)
    losses=[]
    for _ in range(epochs):
        val,params=step(params);losses.append(float(val))
    losses.append(float(loss(params)))
    convert=lambda p:tuple(np.asarray(x,dtype=np.float64) for x in p)
    model=Model(arch,convert(params[0]),convert(params[1]),scale,tuple(losses))
    if not np.allclose(predict(model,rows),predict(reference,rows),rtol=3e-3,atol=2e-4) or not np.allclose(model.losses,reference.losses,rtol=3e-3,atol=2e-4):raise RuntimeError('TPU numerical reference mismatch')
    return model


def tpu_train(rows,*,seed,epochs):
    return _jax_train(rows,seed=seed,epochs=epochs,platform='tpu')


def simulate_tpu(*,seed=42,epochs=16):
    """Execute identical training math on CPU JAX, not TPU timing or hardware."""
    from .neuro_symbolic import fixture
    from .neural import digest
    d=fixture('smooth',seed=seed)
    model=_jax_train(d.train,seed=seed,epochs=epochs,platform='cpu')
    return {'backend':'jax-cpu-simulation','seed':seed,'epochs':epochs,'reference_verified':True,
            'loss_before':model.losses[0],'loss_after':model.losses[-1],'weights_sha256':digest(model)}


def run(kind,seed,budget,index=0):
    if kind not in ('cpu','gpu','tpu') or type(seed) is not int or not 0<=seed<2**32-8 or type(index) is not int or not 0<=index<8 or type(budget) is not int or not 16<=budget<=1024:raise ValueError('cloud worker bounds')
    seed+=index
    if kind=='cpu':
        from .engine import Config,run as evolve
        report=asyncio.run(evolve(Config(seed=seed,generations=min(8,budget//16),islands=2,workers=2,budget=budget,concurrency=1)))
        return {'backend':'cpu','index':index,'seed':seed,'result':report}
    from .neural import BASELINE,digest,predict,rmse
    from .neuro_symbolic import fixture
    d=fixture('smooth',seed=seed);epochs=min(400,budget)
    if kind=='gpu':
        from .training import Trainer
        model=Trainer('cuda',timeout=300).fit(BASELINE,d.train,seed=seed,epochs=epochs)
    else:model=tpu_train(d.train,seed=seed,epochs=epochs)
    return {'backend':kind,'index':index,'seed':seed,'epochs':epochs,'reference_verified':True,'train_loss_before':model.losses[0],'train_loss_after':model.losses[-1],'test_rmse':rmse(predict(model,d.test),d.test),'weights_sha256':digest(model),'model':json.loads(model.to_json())}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=('cpu','gpu','tpu'),required=True);p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int,default=64);a=p.parse_args();idx=int(os.environ.get('JOB_COMPLETION_INDEX','0'));print(json.dumps(run(a.kind,a.seed,a.budget,idx),allow_nan=False))
if __name__=='__main__':main()
