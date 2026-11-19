"""Deterministic testbeds, explicitly separate from native provider adapters.

Models: generated word-expression grammar (not Lean/Isabelle kernels), virtual
Kubernetes capacity/deadlines (not scheduler equivalence), synchronous CPU
replicas executing real LoRA forward/backward (not measured GPU throughput).
"""
from __future__ import annotations
import copy
import hashlib
import random
import re
from .polyglot import Program
from . import bitproof


def check_source(backend: str, source: str, left: Program, right: Program) -> dict:
    """Parse exact generated theorem subset, bind its two terms, run actual SMT.

    Reject anything outside the fixed grammar, including additional commands.
    The result certifies modular IR semantics, not external-language elaboration.
    """
    if not isinstance(left, Program) or not isinstance(right, Program) or type(source) is not str or len(source)>16384:
        raise ValueError('proof model bounds')
    if backend=='lean':
        prefix='import Std.Tactic.BVDecide\nset_option maxHeartbeats 200000\ntheorem omega_extensional_equivalence :\n  (fun (x y : BitVec 16) => '
        separator=') =\n  (fun (x y : BitVec 16) => '
        suffix=') := by\n  funext x y\n  bv_decide\n'
        literal=' : BitVec 16)'
        ops={'+':'add','-':'sub','*':'mul','^^^':'xor','&&&':'and','|||':'or'}
    elif backend=='isabelle':
        prefix=('theory Omega_Proof\n  imports "HOL-Library.Word"\nbegin\ncontext includes bit_operations_syntax\nbegin\nlemma omega_extensional_equivalence:\n'
                '  "(\\<lambda>(x::16 word) (y::16 word). ')
        separator=') = (\\<lambda>(x::16 word) (y::16 word). '
        suffix=')"\n  apply (rule ext)+\n  by (simp add: algebra_simps; (smt (z3)))\nend\nend\n'
        literal=' :: 16 word)'
        ops={'+':'add','-':'sub','*':'mul','XOR':'xor','AND':'and','OR':'or'}
    else:raise ValueError('unsupported proof model')
    if not source.startswith(prefix) or not source.endswith(suffix):raise ValueError('unexpected theorem envelope')
    parts=source[len(prefix):-len(suffix)].split(separator)
    if len(parts)!=2:raise ValueError('two closed functions required')
    def parse(text):
        i=0
        def read(s):
            nonlocal i
            if not text.startswith(s,i):raise ValueError('unexpected expression syntax')
            i+=len(s)
        def term(depth=0):
            nonlocal i
            if depth>8 or i>=len(text):raise ValueError('term depth')
            if text[i] in 'xy':
                op=text[i];i+=1;return (op,)
            read('(')
            m=re.match(r'[0-9]{1,5}',text[i:])
            if m:
                n=int(m.group());i+=len(m.group());read(literal);return ('lit',n)
            a=term(depth+1);read(' ')
            op=next((o for o in ops if text.startswith(o+' ',i)),None)
            if op is None:raise ValueError('unsupported word operator')
            read(op+' ');b=term(depth+1);read(')');return (ops[op],a,b)
        tree=term()
        if i!=len(text):raise ValueError('trailing term')
        return Program(tree)
    a,b=map(parse,parts)
    if a!=left or b!=right:raise ValueError('theorem IR binding mismatch')
    result=bitproof.prove(a,b)
    return {**result,'mode':'DETERMINISTIC-SIMULATION','source_backend':backend,
            'source_sha256':hashlib.sha256(source.encode()).hexdigest(), 'native_kernel_verified':False}


class VirtualCluster:
    """Virtual-time whole-job resource admission, deadlines and API faults.

    No real API or GPU; FIFO admission of entire indexed jobs. No preemption,
    autoscaling, actual pod execution, placement topology, or metering.
    """
    def __init__(self,namespace: str,*,cpu:int,gpu:int,tpu:int,seed:int):
        if type(namespace) is not str or not namespace or any(type(x) is not int or not 0<=x<=32 for x in (cpu,gpu,tpu)) or type(seed) is not int or not 0<=seed<2**32:
            raise ValueError('virtual resource bounds')
        self.namespace=namespace;self.capacity={'cpu':cpu,'gpu':gpu,'tpu':tpu};self.used=dict.fromkeys(self.capacity,0)
        self.identity=hashlib.sha256(repr((namespace,self.capacity,seed)).encode()).hexdigest()
        self.jobs={};self.events=[];self.now=0;self.create_count=0;self.lose_next_create=False
    def _record(self,kind,name):self.events.append((self.now,kind,name,tuple(self.used.items())))
    def _schedule(self):
        for name,row in self.jobs.items():
            if row['phase']!='queued':continue
            kind,units=row['kind'],row['units']
            if self.used[kind]+units<=self.capacity[kind]:
                self.used[kind]+=units;row['phase']='running';self._record('scheduled',name)
    def _terminal(self,name,phase):
        row=self.jobs[name]
        if row['phase']=='running':self.used[row['kind']]-=row['units']
        row['phase']=phase;row['object']['status']={'conditions':[{'type':phase,'status':'True'}]};self._record(phase,name)
    def create(self,body):
        obj=copy.deepcopy(body);meta=obj['metadata'];spec=obj['spec'];name=meta['name']
        if meta['namespace']!=self.namespace or name in self.jobs or len(self.jobs)>=64:raise ValueError('virtual API conflict')
        limits=spec['template']['spec']['containers'][0]['resources']['limits'];kind='gpu' if 'nvidia.com/gpu' in limits else 'tpu' if 'google.com/tpu' in limits else 'cpu'
        units=spec['parallelism']*(int(limits['nvidia.com/gpu']) if kind=='gpu' else int(limits['google.com/tpu']) if kind=='tpu' else 1)
        deadline=spec['activeDeadlineSeconds']
        if type(units) is not int or not 1<=units<=64 or type(deadline) is not int or not 1<=deadline<=7200:raise ValueError('virtual resource request')
        self.create_count+=1;meta['uid']=hashlib.sha256(f'{self.identity}:{name}:{self.create_count}'.encode()).hexdigest()
        self.jobs[name]={'object':obj,'phase':'queued','kind':kind,'units':units,'deadline':self.now+deadline}
        self._record('accepted',name);self._schedule()
        if self.lose_next_create:self.lose_next_create=False;self._record('lost-response',name);raise TimeoutError('virtual response lost after commit')
        return self.get(name)
    def get(self,name):return copy.deepcopy(self.jobs[name]['object']) if name in self.jobs else None
    def advance(self,seconds):
        if type(seconds) is not int or not 0<=seconds<=7200:raise ValueError('virtual clock bounds')
        end=self.now+seconds
        for instant in sorted({r['deadline'] for r in self.jobs.values() if self.now<r['deadline']<=end and r['phase'] in ('queued','running')}):
            self.now=instant
            for name,row in self.jobs.items():
                if row['phase'] in ('queued','running') and row['deadline']<=instant:self._terminal(name,'Failed')
            self._schedule()
        self.now=end
    def complete(self,name):
        if self.jobs[name]['phase']!='running':raise ValueError('job not running')
        self._terminal(name,'Complete');self._schedule()
    def delete(self,name,uid):
        if name not in self.jobs:return None
        row=self.jobs[name]
        if row['object']['metadata']['uid']!=uid:raise ValueError('virtual UID precondition')
        if row['phase']=='running':self.used[row['kind']]-=row['units']
        del self.jobs[name];self._record('deleted',name);self._schedule();return {}


def distributed_step(replicas, rows, *, steps:int, seed:int, unavailable=(), fail_at_step=None):
    """Synchronous uneven-shard allreduce model on actual independent CPU sessions.

    Average by sample count, clip once, one central AdamW update, broadcast.
    Any missing participant aborts before updating; exceptions restore all inputs.
    No native NCCL, network timings, or pretrained large model requirement claim.
    """
    import torch
    from .llm_plasticity import Session
    from .plasticity import validate_record
    if (not isinstance(replicas,(tuple,list)) or not 2<=len(replicas)<=8 or len({id(r) for r in replicas})!=len(replicas) or
            any(not isinstance(r,Session) or r.device!='cpu' for r in replicas) or type(rows) is not tuple or not len(replicas)<=len(rows)<=64 or
            type(steps) is not int or not 1<=steps<=64 or type(seed) is not int or not 0<=seed<2**32 or unavailable or
            (fail_at_step is not None and (type(fail_at_step) is not int or not 0<=fail_at_step<steps))):
        raise ValueError('complete synchronized CPU replica group required')
    rows=tuple(validate_record(r) for r in rows);root=replicas[0];start=root.snapshot()
    if any(r.base_digest()!=root.base_sha or r.snapshot()!=start or r.encoder_id!=root.encoder_id or r.action_ids!=root.action_ids for r in replicas):raise ValueError('replica model or adapter mismatch')
    rng=random.Random(seed);opt=torch.optim.AdamW(list(root.params.values()),lr=.01,weight_decay=0.);events=[]
    try:
        for step in range(steps):
            order=list(range(len(rows)));rng.shuffle(order);shards=[order[i::len(replicas)] for i in range(len(replicas))]
            for r,indices in zip(replicas,shards):
                for param in r.params.values():param.grad=None
                r._backward(r._dataset(tuple(rows[i] for i in indices)))
            if step==fail_at_step:raise RuntimeError('virtual collective interrupted after backward')
            for name in root.params:
                if any(r.params[name].grad is None for r in replicas):raise ValueError('missing gradient')
                grad=sum((r.params[name].grad.detach().clone()*(len(indices)/len(rows)) for r,indices in zip(replicas,shards)))
                if not torch.isfinite(grad).all():raise ValueError('nonfinite collective gradient')
                root.params[name].grad=grad
            torch.nn.utils.clip_grad_norm_(list(root.params.values()),1.,error_if_nonfinite=True);opt.step()
            active=root.snapshot()
            for r in replicas[1:]:r.restore(active)
            events.append({'step':step,'shards':shards})
        if any(r.base_digest()!=root.base_sha for r in replicas):raise ValueError('frozen base changed')
        return {'mode':'DETERMINISTIC-SIMULATION','seed':seed,'steps':steps,'samples':steps*len(rows),'events':events}
    except BaseException:
        for r in replicas:r.restore(start)
        raise
    finally:
        for r in replicas:
            for param in r.params.values():param.grad=None
