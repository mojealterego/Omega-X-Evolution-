"""Finite cellular sheaf diffusion on restricted sections, not an arbitrary GNN.

Energy 1/2 Σ_e weight_e ||R_u x_u - R_v x_v||². Differentiable
quadratic E, graph-Laplacian gradient; CFL bound is a sufficient trace bound,
not a measured convergence rate. No mutable runtime repair/control.
"""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np


def real(x,a,b):
    return type(x) in (int,float) and math.isfinite(x) and a<=x<=b


@dataclass(frozen=True,slots=True)
class SheafEdge:
    u:int
    v:int
    left:tuple[tuple[float,...],...]
    right:tuple[tuple[float,...],...]
    weight:float

    def __post_init__(self):
        if (type(self.u) is not int or type(self.v) is not int or self.u<0 or self.v<0 or self.u==self.v
            or type(self.left) is not tuple or type(self.right) is not tuple or not 1<=len(self.left)==len(self.right)<=8
            or type(self.left[0]) is not tuple or not 1<=len(self.left[0])<=8
            or not real(self.weight,0.,5.)):
            raise ValueError('sheaf edge bounds')
        n=len(self.left[0])
        if any(type(row) is not tuple or len(row)!=n or not all(real(v,-8.,8.) for v in row) for row in self.left+self.right):
            raise ValueError('edge restriction shape')


def _validate(x,edges):
    if (type(x) is not tuple or not 2<=len(x)<=64 or type(x[0]) is not tuple
        or not 1<=len(x[0])<=8 or any(type(row) is not tuple or len(row)!=len(x[0]) or not all(real(v,-1e5,1e5) for v in row) for row in x)
        or type(edges) is not tuple or len(edges)>128):
        raise ValueError('sheaf domain bounds')
    for e in edges:
        if type(e) is not SheafEdge: raise ValueError('edge type')
        e.__post_init__()
        if max(e.u,e.v)>=len(x) or len(e.left[0]) != len(x[0]): raise ValueError('edge domain mismatch')


def _fields(x,edges):
    _validate(x,edges)
    X=np.array(x,dtype=np.float64)
    G=np.zeros_like(X)
    energy=0.
    cfl=0.
    for e in edges:
        a=np.array(e.left);b=np.array(e.right)
        residual=a@X[e.u]-b@X[e.v]
        G[e.u]+=e.weight*a.T@residual
        G[e.v]-=e.weight*b.T@residual
        energy+=.5*e.weight*float(residual@residual)
        cfl+=e.weight*(float(np.sum(a*a))+float(np.sum(b*b)))
    if not np.all(np.isfinite(G)) or not math.isfinite(energy) or not math.isfinite(cfl):
        raise ArithmeticError('nonfinite sheaf operator')
    return energy,G,cfl


def energy(x,edges):
    return _fields(x,edges)[0]


def gradient(x,edges):
    return tuple(tuple(map(float,row)) for row in _fields(x,edges)[1])


def diffuse(x,edges,dt,*,steps=1):
    if not real(dt,1e-10,.5) or type(steps) is not int or not 1<=steps<=256:
        raise ValueError('sheaf step bounds')
    _,g,bound=_fields(x,edges)
    if bound and dt > 1/bound + 1e-14:
        raise ValueError('stability bound exceeded')
    current=x
    for _ in range(steps):
        en,g,b=_fields(current,edges)
        nxt=np.asarray(current,dtype=np.float64)-dt*g
        candidate=tuple(tuple(map(float,row)) for row in nxt)
        new_en=_fields(candidate,edges)[0]
        if new_en>en+1e-9*max(1.,en):
            raise ArithmeticError('energy increased in gradient step')
        current=candidate
    return current
