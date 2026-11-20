"""Fixed synthetic signal regression audit; returns metrics, never learned state."""
import numpy as np


def audit(seed):
    if type(seed) is not int or not 0<=seed<2**32:
        raise ValueError('seed')
    rng=np.random.default_rng(seed)
    # Disjoint generated samples; fixed target projection, no agent trajectories.
    x=rng.uniform(-1,1,(96,2)); y=x@np.array([[.5,-.25],[.25,.5]])
    # Fixed initial comparator, deterministic multirate fitting on train only.
    w=np.zeros((3,2,2)); counts=[0,0,0]
    for t in range(1,65):
        for j,clock in enumerate((1,4,16)):
            if t%clock==0:
                a=x[t-clock:t]; b=y[t-clock:t]
                w[j]-=.5*(a.T@(a@w[j]-b))/clock
                counts[j]+=1
    def mse(a,b,fit):
        return float(np.mean((a@fit-b)**2))
    fit=w.mean(axis=0); zero=np.zeros((2,2)); report={'updates':tuple(counts)}
    for name,sl in [('train',slice(0,64)),('holdout',slice(64,80)),('retention',slice(80,96))]:
        report[name+'_mse']=mse(x[sl],y[sl],fit)
        report['frozen_'+name+'_mse']=mse(x[sl],y[sl],zero)
    report['target_variance']=float(np.var(y[64:80],axis=0).mean())
    report['prediction_variance']=float(np.var(x[64:80]@fit,axis=0).mean())
    report['collapsed']=report['prediction_variance']<.01*report['target_variance']
    return report
