"""Bounded adaptive phenotype geometry; no mutable promotion objective.

A quadtree partitions a normalized 2D AST feature domain. A finite lattice
approximates the Riemannian metric. Distances are shortest-path graph lengths,
not an assertion of exact continuum geodesics or learned physical curvature.
"""
from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import json
import math
from .engine import Archive, Expression, dominates, score


@dataclass(frozen=True)
class TopologyPolicy:
    depth: int = 4
    window: int = 64
    split_count: int = 4
    strength: float = 2.0

    def __post_init__(self):
        if (type(self.depth) is not int or not 2 <= self.depth <= 5 or
            type(self.window) is not int or not 8 <= self.window <= 256 or
            type(self.split_count) is not int or not 2 <= self.split_count <= self.window or
            type(self.strength) not in (int, float) or not math.isfinite(self.strength) or not 0 <= self.strength <= 8):
            raise ValueError('topology policy bounds')


def phenotype(code, size):
    """Log-normalized AST nodes and operations, quantized to mesh vertices."""
    e=Expression(code)
    return tuple(min(size-1, int(math.log1p(v)/math.log(101)*size)) for v in (e.count,e.operations))


def _entropy(counts):
    total=sum(counts.values())
    return -sum((n/total)*math.log(n/total) for n in counts.values()) if total else 0.


class Manifold:
    def __init__(self, policy, codes):
        if not isinstance(policy,TopologyPolicy): raise ValueError('invalid topology policy')
        self.policy=policy; self.size=2**policy.depth
        # Caller supplies bounded recent window; duplicate observations express density.
        codes=list(codes)[-policy.window:]
        self.positions=[phenotype(c,self.size) for c in codes]
        bins={}
        for c,p in zip(codes,self.positions):
            bins.setdefault(p,Counter()).update(type(n).__name__ for n in ast.walk(Expression(c).tree))
        ns=self.size
        self.entropy={}
        for x in range(ns):
            for y in range(ns):
                hist=Counter()
                for i in range(max(0,x-1),min(ns,x+2)):
                    for j in range(max(0,y-1),min(ns,y+2)):
                        hist.update(bins.get((i,j),{}))
                self.entropy[x,y]=_entropy(hist)/math.log(32)
        # Smooth conformal SPD metric: g = exp(2 phi) I.
        # Local entropy and its finite-difference gradient scale metric lengths.
        self.tensors={};self.gradient={};self.phi={}
        for (x,y),h in self.entropy.items():
            dx=(self.entropy[min(ns-1,x+1),y]-self.entropy[max(0,x-1),y])/2
            dy=(self.entropy[x,min(ns-1,y+1)]-self.entropy[x,max(0,y-1)])/2
            a=policy.strength; gradient=math.hypot(dx,dy);base=1+a*(h+gradient*gradient)
            self.gradient[x,y]=gradient;self.phi[x,y]=.5*math.log(base)
            self.tensors[x,y]=(base,0.,base)
        # Gaussian curvature of conformal metric K=-exp(-2phi) laplacian(phi).
        # Centered finite difference on the interior; no extrapolated boundary.
        self.curvature={}
        for x in range(1,ns-1):
            for y in range(1,ns-1):
                v=self.phi[x,y]
                lap=(self.phi[x-1,y]+self.phi[x+1,y]+self.phi[x,y-1]+self.phi[x,y+1]-4*v)*(ns-1)**2
                self.curvature[x,y]=-lap/self.tensors[x,y][0]
        self.leaves=[];self._cells={}
        def split(x,y,width,points):
            # Split only observed diverse populations; rebuild permits coarsening.
            novelty=max((self.entropy[p]+self.gradient[p] for p in points),default=0.)
            min_count=max(2,math.ceil(policy.split_count/(1+policy.strength*novelty)))
            spatial_entropy=_entropy(Counter(points))
            if width>1 and len(points)>=min_count and spatial_entropy>0:
                half=width//2
                for i,j in ((0,0),(0,1),(1,0),(1,1)):
                    u,v=x+i*half,y+j*half
                    split(u,v,half,[p for p in points if u<=p[0]<u+half and v<=p[1]<v+half])
            else:
                cell=(x,y,width);self.leaves.append(cell)
                for i in range(x,x+width):
                    for j in range(y,y+width):self._cells[i,j]=cell
        split(0,0,ns,self.positions)
        self._dist={}

    def cell(self,p):return self._cells[p]

    def distances(self,source):
        if source not in self.tensors:raise ValueError('mesh vertex outside domain')
        if source in self._dist:return self._dist[source]
        dist={source:0.};queue=[(0.,source)]
        while queue:
            d,p=heapq.heappop(queue)
            if d!=dist[p]:continue
            for dx,dy in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
                q=(p[0]+dx,p[1]+dy)
                if q not in self.tensors:continue
                a,b,c=((u+v)/2 for u,v in zip(self.tensors[p],self.tensors[q]))
                cost=math.sqrt(a*dx*dx+2*b*dx*dy+c*dy*dy)/(self.size-1)
                nd=d+cost
                if nd<dist.get(q,math.inf):dist[q]=nd;heapq.heappush(queue,(nd,q))
        # Bound cached all-pairs memory even at 32^2 vertices.
        if len(self._dist)>=16:self._dist.pop(next(iter(self._dist)))
        self._dist[source]=dist;return dist

    def distance(self,a,b):
        if b not in self.tensors:raise ValueError('mesh vertex outside domain')
        return self.distances(a)[b]

    def summary(self):
        payload=[self.leaves, [[*p,*g] for p,g in self.tensors.items()]]
        return {'leaf_count':len(self.leaves),'mesh_vertices':self.size**2,
                'geometry_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                'entropy_max':max(self.entropy.values()),'metric_trace_max':max(a+c for a,_,c in self.tensors.values()),
                'curvature_min':min(self.curvature.values()),'curvature_max':max(self.curvature.values())}


class TopologicalArchive(Archive):
    """Archive with frozen geometry during a transaction and deterministic rebinning."""
    def __init__(self,policy):
        super().__init__(1);self.policy=policy;self.manifold=Manifold(policy,[]);self._features={}

    def _point(self,code):
        if code not in self._features:self._features[code]=phenotype(code,self.manifold.size)
        return self._features[code]

    def cell_for(self,code):return self.cells[0].get(self.manifold.cell(self._point(code)),[])

    def _retain(self,a):
        cell=self.cells[0].setdefault(self.manifold.cell(self._point(a.code)),[])
        if any(dominates(x.metrics,a.metrics) or (x.code==a.code and x.metrics==a.metrics) for x in cell):return
        cell[:]=[x for x in cell if not dominates(a.metrics,x.metrics)]+[a]
        cell.sort(key=lambda x:(-score(x.metrics),x.id));del cell[self.capacity:]

    def add(self,a):
        # Reuse canonical validation/genealogy; temporarily redirect fixed-grid retention.
        live=self.cells;self.cells=[{}]
        try:accepted=super().add(a)
        finally:self.cells=live
        if accepted:self._retain(a)
        return accepted

    def adapt(self):
        recent=list(self.lineage.values())[-self.policy.window:]
        self.manifold=Manifold(self.policy,[a.code for a in recent]);self.cells=[{}]
        for a in self.lineage.values():self._retain(a)

    def sample(self,island,rng):
        if island!=0:raise ValueError('local island index')
        candidates=list(self.lineage.values());champion=self._point(self.best().code)
        dist=self.manifold.distances(champion);weights=[]
        for a in candidates:
            g=a.genome;p=self._point(a.code);cell=self.cell_for(a.code)
            w=1/(1+math.exp(-g.sharpness*(score(a.metrics,g.weights)-g.threshold)))
            weights.append(w/(1+self.children.get(a.id,0))**g.novelty*(1+1/max(1,len(cell)))*(1+dist[p]))
        return rng.choices(candidates,weights)[0]

    def inspiration(self,parent):
        candidates=[a for cell in self.cells[0].values() for a in cell if a.code!=parent.code]
        if not candidates:return parent
        distances=self.manifold.distances(self._point(parent.code))
        return max(candidates,key=lambda a:(score(a.metrics)+.25*distances[self._point(a.code)],a.id))

    def guided_patch(self,parent,rng):
        """Bounded convex recombination or symmetric residual mutation."""
        elite=self.inspiration(parent)
        w=round(rng.uniform(.1,.9),3)
        proposals=[f'({1-w:.3f}*({parent.code})+{w:.3f}*({elite.code}))',
                   f'(({parent.code})-{w:.3f}*abs(x-y))',f'(({parent.code})-{w:.3f})']
        for code in proposals[1:] if elite.code==parent.code else proposals:
            try:Expression(code)
            except ValueError:continue
            return f'<<<<<<< SEARCH\n{parent.code}\n=======\n{code}\n>>>>>>> REPLACE'
        return None

    def summary(self):return self.manifold.summary()
