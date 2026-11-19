"""Operator-authorized, finite local infrastructure orchestration (Linux).
No arbitrary commands, external provisioning, replication or cloud spending.
Durable reservations, bounded child processes, idempotent recovery and stop.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from .checkpoint import CheckpointStore
from .graph_memory import canonical

MAX_RESULT=4*1024*1024


@dataclass(frozen=True)
class Limits:
    total_cpu_seconds:int=60
    max_jobs:int=8
    max_wall_seconds:int=30
    max_parallel:int=4
    memory_mib:int=1024
    def __post_init__(self):
        if any(type(v) is not int for v in asdict(self).values()) or not (1<=self.total_cpu_seconds<=600 and 1<=self.max_jobs<=16 and 1<=self.max_wall_seconds<=120 and 1<=self.max_parallel<=4 and 256<=self.memory_mib<=2048):raise ValueError('infrastructure policy')


@dataclass(frozen=True)
class Job:
    id:str
    kind:str
    cpu_seconds:int=5
    wall_seconds:int=10
    seed:int=42
    budget:int=128
    def __post_init__(self):
        if type(self.id) is not str or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',self.id) or self.kind not in ('axioms','scheduler','plasticity') or any(type(v) is not int for v in (self.cpu_seconds,self.wall_seconds,self.seed,self.budget)) or not (1<=self.cpu_seconds<=60 and 1<=self.wall_seconds<=120 and 0<=self.seed<2**32 and 16<=self.budget<=1024):raise ValueError('job contract')


def _digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


@contextmanager
def _lock(path):
    import fcntl
    fd=os.open(str(path)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);yield
    finally:os.close(fd)


def _worker(job,limits,parent):
    # Trusted fixed dispatcher. Kernel terminates this direct child if the
    # controller dies; recheck to close the prctl/getppid race. Linux only.
    import ctypes
    import resource
    libc=ctypes.CDLL(None,use_errno=True)
    if sys.platform!='linux' or libc.prctl(1,signal.SIGKILL,0,0,0)!=0 or os.getppid()!=parent:raise RuntimeError('parent death guard unavailable')
    signal.alarm(job.wall_seconds)
    resource.setrlimit(resource.RLIMIT_CPU,(job.cpu_seconds,job.cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS,(limits.memory_mib*1024**2,)*2)
    resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_RESULT,MAX_RESULT))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if job.kind=='axioms':
        from .axioms import discover,verify
        result=discover(seed=job.seed,budget=job.budget)
        if not verify(result):raise RuntimeError('axiom report verification failed')
    elif job.kind=='scheduler':
        import asyncio
        from .engine import Config,run
        result=asyncio.run(run(Config(seed=job.seed,generations=min(8,job.budget//16),islands=2,workers=2,budget=job.budget,concurrency=1)))
    elif job.kind=='plasticity':
        from .plasticity import Policy,fixture,fit_adapter,evaluate_adapter
        policy=Policy(seed=job.seed,steps=min(400,job.budget));t,v,r,test=fixture(job.seed,groups=4)
        result=fit_adapter(policy,t,v,r);result['test']=evaluate_adapter(policy,result['adapter'],test)
    else:raise ValueError('unregistered workload')
    data=canonical(result)
    if len(data.encode())>MAX_RESULT:raise ValueError('result cap')
    print(data)


class Orchestrator:
    def __init__(self,path,key,limits,*,create=False):
        if sys.platform!='linux':raise RuntimeError('local Linux resource controls required')
        if not isinstance(limits,Limits):raise ValueError('limits required')
        self.path=Path(path).absolute();self.limits=limits;self._key=key;self.store=CheckpointStore(self.path,key)
        self.stop_path=Path(str(self.path)+'.stop')
        root=Path(__file__).parent
        self.contract=_digest([asdict(limits),list(sys.version_info[:3]),*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('infrastructure.py','axioms.py','plasticity.py','engine.py','proof_kernel.py','holographic.py','swarm.py')]])
        if create:self.store.initialize({'contract':self.contract,'reserved_cpu_seconds':0,'jobs':{}})
        self.inspect()
    def _load(self):
        rev,s=self.store.load()
        if s['contract']!=self.contract:raise ValueError('infrastructure contract mismatch')
        return rev,s
    def _stopped(self):return os.path.lexists(self.stop_path)
    def inspect(self):
        _,state=CheckpointStore(self.path,self._key).load()
        if state['contract']!=self.contract:raise ValueError('infrastructure contract mismatch')
        return {**state,'stopped':self._stopped()}
    def stop(self,*,authorized=False):
        if authorized is not True:raise PermissionError('stop authorization required')
        # The existence of this private operator-owned marker is fail-closed.
        # Deliberately irreversible for this ledger, even if its write is truncated.
        try:fd=os.open(self.stop_path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        except FileExistsError:return
        try:os.write(fd,b'STOP\n');os.fsync(fd)
        finally:os.close(fd)
        d=os.open(self.stop_path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(d)
        finally:os.close(d)
    def _recover(self,rev,s):
        changed=False
        for row in s['jobs'].values():
            if row['status']=='reserved':row['status']='interrupted';changed=True
        if changed:rev+=1;self.store.save(rev,s)
        return rev,s
    def recover(self,*,authorized=False):
        if authorized is not True:raise PermissionError('recovery authorization required')
        with _lock(self.path):self._recover(*self._load());return self.inspect()
    def run(self,job,*,authorized=False):return self.run_batch((job,),authorized=authorized)[0]
    def run_batch(self,jobs,*,authorized=False,live_telemetry=False):
        if authorized is not True:raise PermissionError('explicit execution authorization required')
        if type(jobs) is not tuple or not 1<=len(jobs)<=self.limits.max_jobs or any(not isinstance(j,Job) for j in jobs) or len({j.id for j in jobs})!=len(jobs) or type(live_telemetry) is not bool:raise ValueError('batch contract')
        with _lock(self.path):
            rev,s=self._recover(*self._load());new=[]
            for job in jobs:
                if job.id in s['jobs']:
                    if s['jobs'][job.id]['job']!=asdict(job):raise ValueError('conflicting job id')
                    continue
                if self._stopped():raise ValueError('orchestrator stopped')
                if job.wall_seconds>self.limits.max_wall_seconds:raise ValueError('wall time policy')
                new.append(job)
            if not new:return [s['jobs'][j.id] for j in jobs]
            if len(s['jobs'])+len(new)>self.limits.max_jobs or s['reserved_cpu_seconds']+sum(j.cpu_seconds for j in new)>self.limits.total_cpu_seconds:raise ValueError('resource budget exhausted')
            # Atomic batch reservation before any launch; never refund or silently replay.
            for job in new:s['jobs'][job.id]={'job':asdict(job),'status':'reserved','result':None}
            s['reserved_cpu_seconds']+=sum(j.cpu_seconds for j in new);rev+=1;self.store.save(rev,s)
            pending=list(new);active={};peak=0
            with tempfile.TemporaryDirectory(prefix='omega-work-') as temp:
                try:
                    while pending or active:
                        stopped=self._stopped();parallel=self.limits.max_parallel
                        if live_telemetry and not stopped:
                            from .epigenetics import Telemetry
                            t=Telemetry.sample(min(100,100*len(active)//self.limits.max_parallel))
                            if max(t.cpu,t.memory)>=85:parallel=1
                        while pending and len(active)<parallel and not stopped and not self._stopped():
                            job=pending.pop(0);out=Path(temp)/f'{job.id}.out';err=Path(temp)/f'{job.id}.err'
                            try:
                                env={'PATH':os.defpath,'LANG':'C.UTF-8','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONPATH':str(Path(__file__).resolve().parent.parent)}
                                with out.open('wb') as f,err.open('wb') as e:
                                    proc=subprocess.Popen([sys.executable,'-m','omega_x_evolution.infrastructure','--worker',canonical([asdict(job),asdict(self.limits),os.getpid()])],cwd=temp,env=env,stdin=subprocess.DEVNULL,stdout=f,stderr=e,close_fds=True,start_new_session=True)
                                active[job.id]=(job,proc,time.monotonic(),out);peak=max(peak,len(active))
                            except OSError:s['jobs'][job.id]['status']='launch-failed';rev+=1;self.store.save(rev,s)
                        if self._stopped():
                            for job in pending:s['jobs'][job.id]['status']='cancelled'
                            if pending:pending.clear();rev+=1;self.store.save(rev,s)
                        for ident,(job,proc,start,out) in list(active.items()):
                            status=None;code=proc.poll()
                            if self._stopped():status='cancelled'
                            elif time.monotonic()-start>=job.wall_seconds:status='timeout'
                            elif code is not None:status='succeeded' if code==0 else 'failed'
                            if status is None:continue
                            if proc.poll() is None:proc.kill()
                            code=proc.wait(timeout=5);result=None
                            if status=='succeeded':
                                try:
                                    with out.open('rb') as f:data=f.read(MAX_RESULT+1)
                                    if len(data)>MAX_RESULT:raise ValueError('result cap')
                                    result=json.loads(data)
                                    if type(result) is not dict:raise ValueError('result schema')
                                except (ValueError,OSError,RecursionError):status='failed';result=None
                            s['jobs'][ident].update(status=status,result=result,exit_code=code,wall_seconds=time.monotonic()-start,pid=proc.pid)
                            del active[ident];rev+=1;self.store.save(rev,s)
                        if active:time.sleep(.02)
                finally:
                    for _,proc,_,_ in active.values():
                        if proc.poll() is None:proc.kill()
                        proc.wait(timeout=5)
            s['last_peak_parallel']=peak;rev+=1;self.store.save(rev,s)
            return [s['jobs'][job.id] for job in jobs]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--worker');p.add_argument('--db',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--policy',type=Path);p.add_argument('--authorize',action='store_true')
    p.add_argument('--create',action='store_true');p.add_argument('--stop',action='store_true');p.add_argument('--recover',action='store_true');p.add_argument('--jobs',type=Path);p.add_argument('--live-telemetry',action='store_true');a=p.parse_args()
    if a.worker is not None:
        if len(a.worker)>8192:p.error('worker input cap')
        j,l,parent=json.loads(a.worker);_worker(Job(**j),Limits(**l),parent);return
    if not all((a.db,a.key_file,a.policy)):p.error('db, key-file, policy required')
    def read(path):
        with path.open('rb') as f:data=f.read(16385)
        if len(data)>16384:raise ValueError('file cap')
        return json.loads(data)
    if a.create and not a.authorize:p.error('explicit create authorization required')
    with a.key_file.open('rb') as f:key=f.read(4097)
    if not 32<=len(key)<=4096:raise ValueError('key size')
    o=Orchestrator(a.db,key,Limits(**read(a.policy)),create=a.create)
    if sum(bool(x) for x in (a.stop,a.recover,a.jobs))>1:p.error('choose one operation')
    if a.stop:o.stop(authorized=a.authorize);result=o.inspect()
    elif a.recover:result=o.recover(authorized=a.authorize)
    elif a.jobs:result=o.run_batch(tuple(Job(**x) for x in read(a.jobs)),authorized=a.authorize,live_telemetry=a.live_telemetry)
    else:result=o.inspect()
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
