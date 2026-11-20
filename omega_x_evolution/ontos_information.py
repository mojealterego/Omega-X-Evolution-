"""Offline finite-channel information diagnostics; no policy execution."""
import math
from .ontos_metabolism import channel, probability, mix, entropy, kl, number


def capacity(g, *, iterations=512, tolerance=1e-9):
    """Blahut-Arimoto with a mutual-information lower and dual upper bound."""
    g=channel(g)
    if type(iterations) is not int or not 1<=iterations<=4096 or not number(tolerance,1e-12,.1) or iterations*len(g)*len(g[0])>2_000_000:
        raise ValueError('capacity work bound')
    p=tuple(1/len(g) for _ in g)
    for step in range(1,iterations+1):
        q=mix(p,g); d=tuple(kl(row,q) for row in g)
        low=max(0.,math.fsum(x*y for x,y in zip(p,d))/math.log(2))
        high=max(low,max(d)/math.log(2))
        if high-low<=tolerance or step==iterations:
            return {'lower_bits':low,'upper_bits':high,'prior':p,'converged':high-low<=tolerance,'iterations':step}
        weights=tuple(max(1e-300,x*math.exp(y-max(d))) for x,y in zip(p,d))
        total=math.fsum(weights); p=tuple(x/total for x in weights)


def free_energy(prior,transition,likelihood,preferences,*,observation):
    """One specified simulated action, EFE=risk-IG, exact posterior VFE (bits).

    This is a finite diagnostic convention, not a full Active Inference agent.
    Impossible observations produce an explicit abstention; no environment action.
    """
    prior=probability(prior); prefs=probability(preferences)
    t=channel(transition,len(prior)); predicted=mix(prior,t)
    o=channel(likelihood,len(predicted))
    if len(predicted)!=len(prefs) or any(x==0 for x in prefs) or type(observation) is not int or not 0<=observation<len(o[0]):
        raise ValueError('free energy domain')
    qo=mix(predicted,o)
    risk=max(0.,kl(predicted,prefs)/math.log(2))
    ig=max(0.,entropy(qo)-math.fsum(p*entropy(row) for p,row in zip(predicted,o)))
    evidence=qo[observation]
    posterior=None if evidence==0 else tuple(p*row[observation]/evidence for p,row in zip(predicted,o))
    return {'risk_bits':risk,'information_gain_bits':ig,'efe_bits':risk-ig,'posterior':posterior,'vfe_bits':None if evidence==0 else -math.log2(evidence),'abstain':evidence==0}
