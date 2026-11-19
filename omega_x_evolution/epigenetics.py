"""Reversible activation of optional search blocks; mandatory gates are immutable."""
from __future__ import annotations
from dataclasses import dataclass
import argparse
import json
import math

OPTIONAL = ('neural', 'associative', 'guided')
MANDATORY = ('ast', 'formal', 'cascade', 'audit', 'budget', 'quorum')

@dataclass(frozen=True)
class Telemetry:
    cpu: int
    memory: int
    queue: int
    def __post_init__(self):
        if any(type(x) is not int or not 0 <= x <= 100 for x in (self.cpu,self.memory,self.queue)):
            raise ValueError('telemetry must be integer percentages')

    @classmethod
    def sample(cls,queue:int):
        """Measure host CPU utilization and memory percentage (not cgroup RSS)."""
        import psutil
        if type(queue) is not int or not 0<=queue<=100:raise ValueError('queue percentage')
        return cls(math.ceil(psutil.cpu_percent(interval=.05)),math.ceil(psutil.virtual_memory().percent),queue)

class Switchboard:
    """High pressure disables immediately; two low-pressure samples restore.
    Mid-band samples retain mask but reset recovery streak. Operator allowlist
    may restrict only optional blocks, never weaken mandatory gates.
    """
    def __init__(self, allowed=OPTIONAL):
        if type(allowed) is not tuple or len(set(allowed))!=len(allowed) or not set(allowed)<=set(OPTIONAL):
            raise ValueError('unknown optional block')
        self.allowed=tuple(x for x in OPTIONAL if x in allowed)
        self._enabled=self.allowed;self._streak=0;self._revision=0
    def state(self):
        return {'revision':self._revision,'enabled':list(self._enabled),'mandatory':list(MANDATORY),'recovery_streak':self._streak}
    def update(self, sample:Telemetry):
        if not isinstance(sample,Telemetry):raise ValueError('typed telemetry required')
        pressure=max(sample.cpu,sample.memory,sample.queue)
        if pressure>=85:self._enabled=();self._streak=0
        elif pressure<=50:
            self._streak=min(2,self._streak+1)
            if self._streak==2:self._enabled=self.allowed
        else:self._streak=0
        self._revision+=1
        return self.state()


CLUSTER_OPTIONAL = ('tensor', 'holographic', 'topological')


def cluster_mask(history, allowed):
    """Pure replay of signed/persisted pressure observations; gates never switch off."""
    if type(allowed) is not tuple or not set(allowed)<=set(CLUSTER_OPTIONAL) or len(set(allowed))!=len(allowed) or len(history)>100:
        raise ValueError('cluster mask contract')
    enabled=allowed; streak=0; trace=[]
    for raw in history:
        t=Telemetry(**raw);pressure=max(t.cpu,t.memory,t.queue)
        if pressure>=85:enabled=();streak=0
        elif pressure<=50:
            streak=min(2,streak+1)
            if streak==2:enabled=allowed
        else:streak=0
        trace.append({'sample':raw,'enabled':list(enabled),'recovery_streak':streak,'mandatory':list(MANDATORY)})
    return trace

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--samples',default='[[90,20,20],[30,30,30],[30,30,30]]');a=p.parse_args()
    if len(a.samples)>8192:raise ValueError('sample size')
    xs=json.loads(a.samples)
    if not isinstance(xs,list) or not 1<=len(xs)<=128:raise ValueError('sample count')
    b=Switchboard();print(json.dumps([b.update(Telemetry(*x)) for x in xs],indent=2))
if __name__=='__main__':main()
