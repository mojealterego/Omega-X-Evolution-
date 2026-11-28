"""Deterministic, bounded coevolution. Candidate expressions are interpreted, never exec'd."""
from __future__ import annotations

import ast
import asyncio
from contextlib import nullcontext
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from dataclasses import asdict, dataclass, replace
import hashlib
import hmac
import json
import math
import operator
from pathlib import Path
import random
import re
import secrets
import sys
from typing import Awaitable, Callable
from .checkpoint import CheckpointError, CheckpointStore
from .workers import EvaluationInput, evaluate_batch

BASELINE = '-(x+y)'
WEIGHTS = (.7, .15, .15, 0.)  # immutable promotion objective
VERSION = 'scheduler-ratio-v1'
Metrics = tuple[float, float, float, float]
BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
FUN = {'abs': (1, abs), 'min': (2, min), 'max': (2, max)}


class Expression:
    def __init__(self, source: str):
        if not isinstance(source, str) or len(source) > 2048 or not source.strip():
            raise ValueError('invalid source size')
        try:
            self.tree = ast.parse(source, mode='eval').body
        except (SyntaxError, RecursionError) as exc:
            raise ValueError('invalid syntax') from exc
        self.count = 0
        self.operations = 0
        self._validate(self.tree, 0)
        self.descriptor = (min(9, self.count//5), min(9, self.operations//3))

    def _validate(self, n: ast.AST, depth: int) -> None:
        self.count += 1
        if depth > 14 or self.count > 100:
            raise ValueError('AST budget exceeded')
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            if abs(n.value) <= 1e6 and math.isfinite(n.value):
                return
        elif isinstance(n, ast.Name) and n.id in ('x', 'y'):
            return
        elif isinstance(n, ast.BinOp) and type(n.op) in BIN:
            self.operations += 1
            self._validate(n.left, depth+1); self._validate(n.right, depth+1); return
        elif isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            self.operations += 1
            self._validate(n.operand, depth+1); return
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in FUN:
            if len(n.args) == FUN[n.func.id][0] and not n.keywords:
                self.operations += 1
                for a in n.args: self._validate(a, depth+1)
                return
        raise ValueError('forbidden AST node')

    def evaluate(self, x: float, y: float) -> float:
        if not all(math.isfinite(v) and 0 <= v <= 1 for v in (x,y)):
            raise ValueError('ratios outside domain')
        def walk(n):
            if isinstance(n, ast.Constant): v = float(n.value)
            elif isinstance(n, ast.Name): v = x if n.id == 'x' else y
            elif isinstance(n, ast.BinOp): v = BIN[type(n.op)](walk(n.left), walk(n.right))
            elif isinstance(n, ast.UnaryOp): v = -walk(n.operand) if isinstance(n.op, ast.USub) else walk(n.operand)
            elif isinstance(n, ast.Call): v = FUN[n.func.id][1](*(walk(a) for a in n.args))
            else: raise ValueError('unknown node')
            if not math.isfinite(v) or abs(v) > 1e12: raise ValueError('numeric bound exceeded')
            return v
        return walk(self.tree)


def apply_patch(source: str, patch: str) -> str:
    if not isinstance(patch,str) or len(patch)>8192: raise ValueError('patch size')
    m = re.fullmatch(r'<<<<<<< SEARCH\n([^\n]+)\n=======\n([^\n]+)\n>>>>>>> REPLACE\s*', patch)
    if not m or source != m[1]: raise ValueError('patch must replace exactly the whole mutable expression')
    return m[2]


class ImmutableAuditKernel:
    def __init__(self, key: bytes, evaluator_version: str, source_path: Path | None = None):
        if len(key)<32: raise ValueError('weak key')
        self._key=key; self.version=evaluator_version; self._pending={}
        self._source_path=source_path
        self._source_mac=self._digest_source()
        from .safety_synthesis import RuleBook
        self.rules=RuleBook()
        self._formal_sources={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).digest() for name in ('engine.py','modal.py','interval_checker.py','safety_synthesis.py')}

    def _digest_source(self):
        return hmac.new(self._key,self._source_path.read_bytes(),hashlib.sha256).digest() if self._source_path else b""

    def integrity_ok(self):
        try: return hmac.compare_digest(self._source_mac,self._digest_source()) and all(hmac.compare_digest(d,hashlib.sha256(Path(__file__).with_name(n).read_bytes()).digest()) for n,d in self._formal_sources.items())
        except OSError: return False

    def _mac(self, session, source, metrics, nonce, proof):
        body=json.dumps([self.version,session,source,metrics,nonce,proof],allow_nan=False,separators=(',',':')).encode()
        return hmac.new(self._key,body,hashlib.sha256).hexdigest()

    def issue(self, session: str, source: str, metrics: Metrics) -> str:
        if not self.integrity_ok(): raise ValueError("evaluator integrity failure")
        if session in self._pending: raise ValueError('duplicate pending session')
        from .safety_synthesis import prove,verify
        cert=self.rules.lookup(source) or prove(source)
        if not verify(source,cert):raise ValueError('formal safety proof failed')
        evidence={'certificate':cert,'derived_obligations':self.rules.matches(source)}
        nonce=secrets.token_hex(16); token=self._mac(session,source,metrics,nonce,evidence)
        self._pending[session]=(nonce,evidence)
        return token

    def verify(self, token, session, source, metrics):
        pending=self._pending.get(session)
        if pending is None or not isinstance(token,str) or not self.integrity_ok(): return False
        nonce,evidence=pending;cert=evidence['certificate']
        from .safety_synthesis import verify
        if not verify(source,cert) or not hmac.compare_digest(token,self._mac(session,source,metrics,nonce,evidence)): return False
        self.rules.learn(source,cert)
        del self._pending[session]; return True


# Compatibility name, not a separate or weaker audit implementation.
Audit=ImmutableAuditKernel


@dataclass(frozen=True)
class Result:
    stage: int
    metrics: Metrics=(0.,0.,0.,0.)
    reason: str=''


def oracle(x,y):
    # Fixed surrogate for the document's ratio objective, regularized at zero.
    return -(x+y+(x+.01)/(y+.01)+(y+.01)/(x+.01))


class Cascade:
    def __init__(self, seed: int):
        rng=random.Random(seed)
        self.challenge=[(0.,0.),(0.,1.),(1.,0.),(.01,.99),(.5,.5)]
        self.challenge += [(rng.random(),rng.random()) for _ in range(20)]
        self.failures={p:0 for p in self.challenge}
        self.grid=tuple((rng.random(),rng.random()) for _ in range(96))
        self.holdout=tuple((rng.random(),rng.random()) for _ in range(128))

    def advance(self, seed):
        rng=random.Random(seed)
        ranked=sorted(self.failures,key=lambda p:(-self.failures[p],p))[:24]
        new=[(rng.choice([0.,.001,.01,.5,1.]),rng.random()) for _ in range(8)]
        self.challenge=list(dict.fromkeys([(0.,0.),(0.,1.),(1.,0.),(.5,.5)] + ranked+new))
        self.failures={p:self.failures.get(p,0) for p in self.challenge}

    def _quality(self, expr, grid):
        error=sum(abs(expr.evaluate(x,y)-oracle(x,y))/(1+abs(oracle(x,y))) for x,y in grid)/len(grid)
        return max(0.,1.-error)

    def evaluate(self, code: str) -> Result:
        try: expr=Expression(code)
        except ValueError as e: return Result(0,reason=str(e))
        from .safety_synthesis import prove
        certificate=prove(code)
        if not certificate['proved']:return Result(1,reason='formal safety: '+certificate['reason'])
        # The all-domain proof now discharges the old three-point numerical
        # smoke test. Behavioral properties and fitness remain separate gates.
        valid=0
        for x,y in self.challenge:
            try:
                v=expr.evaluate(x,y); w=expr.evaluate(y,x); z=(x+y)/2
                ok=math.isclose(v,w,abs_tol=1e-8,rel_tol=1e-8) and expr.evaluate(z,z)>=v-1e-8
            except (ValueError,ArithmeticError): ok=False
            if ok: valid+=1
            else: self.failures[(x,y)]+=1
        # Mandatory invariants; do not allow the mutable genome to lower this gate.
        if valid != len(self.challenge): return Result(2,reason='property gate')
        try: quality=self._quality(expr,self.grid)
        except (ArithmeticError,ValueError): return Result(3,reason='benchmark error')
        # deterministic operation cost proxy, not runtime measurement
        return Result(3,(quality,1/(1+expr.operations/30),max(0.,1-expr.count/100),1.))

    def heldout(self, code):
        try: return self._quality(Expression(code),self.holdout)
        except (ValueError,ArithmeticError): return None


@dataclass(frozen=True)
class Genome:
    sharpness: float=10.
    threshold: float=.5
    novelty: float=1.
    weights: Metrics=WEIGHTS
    def mutate(self,rng):
        w=[max(.01,x*rng.uniform(.85,1.15)) for x in self.weights[:3]]; total=sum(w)
        return Genome(min(30,max(2,self.sharpness*rng.uniform(.85,1.15))),min(.9,max(.1,self.threshold+rng.uniform(-.08,.08))),min(2.5,max(.3,self.novelty*rng.uniform(.85,1.15))),tuple(x/total for x in w)+(0.,))


def score(m, w=WEIGHTS): return sum(x*y for x,y in zip(m,w))
def dominates(a,b): return all(x>=y for x,y in zip(a,b)) and any(x>y for x,y in zip(a,b))


@dataclass(frozen=True)
class Artifact:
    id: str
    parent: str|None
    island: int
    generation: int
    code: str
    genome: Genome
    metrics: Metrics


class Archive:
    def __init__(self,islands,capacity=4):
        if islands<1 or capacity<1: raise ValueError('invalid archive')
        self.cells=[{} for _ in range(islands)]; self.lineage={}; self.children={}; self.capacity=capacity
    def add(self,a):
        if a.id in self.lineage: return False
        if not 0<=a.island<len(self.cells) or len(a.metrics)!=4 or any(not math.isfinite(x) or not 0<=x<=1 for x in a.metrics) or a.metrics[3]!=1.: raise ValueError('unqualified artifact')
        if a.parent is not None and a.parent not in self.lineage: raise ValueError('missing ancestor')
        d=Expression(a.code).descriptor
        self.lineage[a.id]=a
        if a.parent: self.children[a.parent]=self.children.get(a.parent,0)+1
        cell=self.cells[a.island].setdefault(d,[])
        if any(dominates(x.metrics,a.metrics) or (x.code==a.code and x.metrics==a.metrics) for x in cell): return True
        cell[:]=[x for x in cell if not dominates(a.metrics,x.metrics)]+[a]
        cell.sort(key=lambda x:(-score(x.metrics),x.id)); del cell[self.capacity:]
        return True
    def sample(self,island,rng):
        candidates=[a for a in self.lineage.values() if a.island==island]
        weights=[]
        for a in candidates:
            g=a.genome; d=Expression(a.code).descriptor
            weights.append((1/(1+math.exp(-g.sharpness*(score(a.metrics,g.weights)-g.threshold))))/(1+self.children.get(a.id,0))**g.novelty*(1+1/max(1,len(self.cells[island].get(d,[])))))
        return rng.choices(candidates,weights)[0]
    def best(self,island=None):
        return max((a for a in self.lineage.values() if island is None or a.island==island),key=lambda a:(score(a.metrics),a.id))
    def migrate(self,generation):
        originals=[self.best(i) for i in range(len(self.cells))]
        for a in originals:
            target=(a.island+1)%len(self.cells)
            if target!=a.island: self.add(replace(a,id=f'm{generation}-{a.island}',parent=a.id,island=target,generation=generation))


@dataclass
class Arm:
    id: str
    tier: str
    cost: int
    pulls: int=0
    wins: int=0


class Router:
    def __init__(self,arms,budget):
        if budget<0 or not arms or len({a.id for a in arms})!=len(arms) or any(a.cost<=0 or a.tier not in ('fast','deep') for a in arms): raise ValueError('invalid routing configuration')
        self.arms=arms; self.budget=budget; self.spent=0
    def select(self,rng,deep):
        feasible=[a for a in self.arms if self.spent+a.cost<=self.budget]
        if not feasible:return None
        total=sum(a.pulls for a in self.arms)
        a=max(feasible,key=lambda a:rng.betavariate(a.wins+1,a.pulls-a.wins+1)+.4*math.sqrt(math.log(total+2)/(a.pulls+1))+.3*(a.tier==('deep' if deep else 'fast'))-.08*math.log1p(a.cost))
        self.spent+=a.cost; a.pulls+=1; return a


@dataclass(frozen=True)
class Trial:
    parent: str
    prompt: str
    patch: str
    score: float
    baseline: float
    accepted: bool
    version: str


class Distillation:
    def __init__(self,margin=.01): self.margin=margin; self.trials=[]; self.sft=[]
    def add(self,t):
        self.trials.append(t)
        if t.accepted and t.score-t.baseline>=self.margin:self.sft.append(t)
    def pairs(self):
        out=[]
        for t in self.sft:
            for bad in self.trials:
                if (t.parent,t.prompt,t.version)==(bad.parent,bad.prompt,bad.version) and t.patch!=bad.patch and t.score-bad.score>=self.margin:
                    out.append({'prompt':t.prompt,'chosen':t.patch,'rejected':bad.patch});break
        return out


@dataclass(frozen=True)
class Config:
    seed:int=101
    generations:int=5
    islands:int=3
    workers:int=3
    budget:int=1000
    concurrency:int=4
    proposal_timeout:float=30.
    def __post_init__(self):
        if not (1<=self.generations<=100 and 1<=self.islands<=16 and 1<=self.workers<=16 and 1<=self.concurrency<=32 and 0<=self.budget<=1000000 and 0<self.proposal_timeout<=300):raise ValueError('configuration outside limits')


Proposal = Callable[[str,str,int],Awaitable[str]]


async def simulated_proposal(model,prompt,seed):
    """Explicit offline mutation operator, not an LLM."""
    parent=json.loads(prompt)['parent']; rng=random.Random(seed)
    a=round(rng.uniform(.2,3),3); b=round(rng.uniform(.005,.1),4); c=round(rng.uniform(.1,3),3)
    choices=[f'-(x+y+{a}*abs(x-y)+{c})',f'-(x+y+{a}*(x-y)*(x-y)+{c})',f'-(x+y+{a}*max(x,y)+{c})',f'-(x+y+{a}*abs(x-y)/(x+y+{b})+{c})',f'-(x+y+{a}*(x-y)*(x-y)/({b}+x*y)+{c})',f'-(x+y+{a}*(x-y)*(x-y)/({b}+min(x,y))+{c})']
    candidate=choices[rng.randrange(len(choices) if model=='deep' else 4)]
    if seed%7==0: candidate='__import__("os")'
    return f'<<<<<<< SEARCH\n{parent}\n=======\n{candidate}\n>>>>>>> REPLACE'


def _checkpoint_contract(cfg: Config) -> dict:
    config = asdict(cfg)
    del config['generations']  # absolute generation target may be extended
    return {'schema': 1, 'benchmark': VERSION, 'config': config,
            'python': list(sys.version_info[:3]),
            'engine_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'storage_sha256': hashlib.sha256(Path(__file__).with_name('checkpoint.py').read_bytes()).hexdigest(),
            'workers_sha256': hashlib.sha256(Path(__file__).with_name('workers.py').read_bytes()).hexdigest(),
            'formal_sha256': {n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ('modal.py','interval_checker.py','safety_synthesis.py')}}


def _snapshot(contract, rng, cascade, archive, router, buf, attempts, rejects, best, stagnation, stopped):
    return {'contract': contract, 'rng': rng.getstate(),
            'lineage': [asdict(a) for a in archive.lineage.values()],
            'challenge': [[list(p), cascade.failures[p]] for p in cascade.challenge],
            'arms': [asdict(a) for a in router.arms], 'spent': router.spent,
            'trials': [asdict(t) for t in buf.trials],
            'attempts': attempts, 'rejects': rejects, 'best': best,
            'stagnation': stagnation, 'stopped': stopped}


def _restore(state, contract, rng, cascade, archive, router, buf):
    if state.get('contract') != contract:
        raise CheckpointError('checkpoint configuration or runtime incompatible')
    try:
        version, inner, gauss = state['rng']
        rng.setstate((version, tuple(inner), gauss))
        for item in state['lineage']:
            data = dict(item)
            genome = dict(data.pop('genome'))
            genome['weights'] = tuple(genome['weights'])
            data['metrics'] = tuple(data['metrics'])
            if not archive.add(Artifact(genome=Genome(**genome), **data)):
                raise ValueError('duplicate artifact')
        cascade.challenge = [tuple(p) for p, _ in state['challenge']]
        cascade.failures = {tuple(p): n for p, n in state['challenge']}
        restored = [Arm(**a) for a in state['arms']]
        if [(a.id,a.tier,a.cost) for a in router.arms] != [(a.id,a.tier,a.cost) for a in restored]:
            raise ValueError('invalid router arms')
        router.arms = restored
        router.spent = state['spent']
        for t in state['trials']:
            buf.add(Trial(**t))
        attempts, rejects, best, stagnation, stopped = (state[k] for k in ('attempts','rejects','best','stagnation','stopped'))
        if not (0 <= rejects <= attempts == sum(a.pulls for a in restored)
                and router.spent == sum(a.cost*a.pulls for a in restored) <= router.budget
                and all(0 <= a.wins <= a.pulls for a in restored)
                and best == score(archive.best().metrics)
                and type(stopped) is bool and stagnation >= 0):
            raise ValueError('inconsistent counters')
        return attempts, rejects, best, stagnation, stopped
    except (KeyError, TypeError, ValueError, IndexError, OverflowError) as exc:
        raise CheckpointError('invalid checkpoint state') from exc


async def run(cfg: Config, proposal: Proposal=simulated_proposal, *, checkpoint: CheckpointStore | None = None, resume: bool = False, evaluation_processes: int = 1, performance_policy=None):
    if type(evaluation_processes) is not int or not 1 <= evaluation_processes <= 32:
        raise ValueError('evaluation_processes must be between 1 and 32')
    if evaluation_processes == 1:
        return await _run(cfg, proposal, checkpoint=checkpoint, resume=resume, executor=None, performance_policy=performance_policy)
    with ProcessPoolExecutor(max_workers=evaluation_processes, mp_context=get_context('spawn')) as executor:
        return await _run(cfg, proposal, checkpoint=checkpoint, resume=resume, executor=executor, performance_policy=performance_policy)


async def _run(cfg: Config, proposal: Proposal, *, checkpoint: CheckpointStore | None, resume: bool, executor, performance_policy=None):
    if resume and checkpoint is None:
        raise ValueError('resume requires checkpoint')
    memory=None
    if type(proposal).__module__==__package__+'.engine_memory':
        from .engine_memory import MemoryProposal
        if type(proposal) is MemoryProposal: memory=proposal
    if checkpoint is not None and proposal is not simulated_proposal and memory is None:
        raise ValueError('checkpoint replay currently supports offline proposals only')
    if memory is not None and checkpoint is not None and performance_policy is not None:
        raise ValueError('wall-clock performance policy cannot promise deterministic memory replay')
    def source_guard(): return memory.guard() if memory is not None else nullcontext()
    with source_guard(): pass
    from . import performance
    if performance_policy is not None and (not isinstance(performance_policy,performance.Policy) or min(cfg.generations*cfg.islands*cfg.workers,cfg.budget)>performance.MAX_ATTEMPTS):
        raise ValueError('invalid performance policy or profiling attempt cap')
    rng=random.Random(cfg.seed); cascade=Cascade(cfg.seed); archive=Archive(cfg.islands)
    perf_context=performance.context(cascade.grid,performance_policy) if performance_policy is not None else None
    perf_records=[]
    audit=Audit(secrets.token_bytes(32),VERSION,Path(__file__)); router=Router([Arm('fast','fast',1),Arm('deep','deep',5)],cfg.budget); buf=Distillation()
    baseline=cascade.evaluate(BASELINE).metrics
    from .safety_synthesis import prove,RuleBook
    audit.rules.learn(BASELINE,prove(BASELINE))
    rejects=attempts=0; best=score(baseline); stagnation=0; sem=asyncio.Semaphore(cfg.concurrency)
    completed=0; stopped=False
    contract=_checkpoint_contract(cfg) if checkpoint is not None else None
    if contract is not None and memory is not None: contract['memory_proposal']=memory.contract()
    if contract is not None and perf_context is not None: contract['performance_regression']=perf_context
    def snapshot():
        state=_snapshot(contract,rng,cascade,archive,router,buf,attempts,rejects,best,stagnation,stopped)
        state['safety_rules']=audit.rules.snapshot()
        if perf_context is not None: state['performance_records']=perf_records
        return state
    if resume:
        with source_guard(): completed,state=checkpoint.load()
        if completed>cfg.generations:
            raise CheckpointError('requested target predates checkpoint')
        attempts,rejects,best,stagnation,stopped=_restore(state,contract,rng,cascade,archive,router,buf)
        audit.rules=RuleBook(state['safety_rules'])
        if perf_context is not None:
            perf_records=state.get('performance_records')
            if type(perf_records) is not list or len(perf_records)>attempts or len(perf_records)>performance.MAX_ATTEMPTS:
                raise CheckpointError('invalid performance history')
    else:
        for i in range(cfg.islands):archive.add(Artifact(f'seed-{i}',None,i,0,BASELINE,Genome(),baseline))
        if checkpoint is not None:
            with source_guard(): checkpoint.initialize(snapshot())
    async def request(arm,prompt,seed):
        async with sem:
            if memory is not None: return await memory(arm.id,prompt,seed)
            try:return await asyncio.wait_for(proposal(arm.id,prompt,seed),cfg.proposal_timeout)
            except Exception:return None
    for gen in range(completed+1,cfg.generations+1) if not stopped else ():
        jobs=[]
        # Plan in fixed order and commit in fixed order independent of provider completion.
        for i in range(cfg.islands):
            for w in range(cfg.workers):
                p=archive.sample(i,rng); arm=router.select(rng,stagnation>=2 or w==0)
                if arm is None:break
                prompt=json.dumps({'parent':p.code,'inspiration':archive.best(i).code,'contract':'Return one exact SEARCH/REPLACE expression patch over x,y in [0,1]. Only +,-,*,/,abs,min,max permitted.'},sort_keys=True)
                seed=rng.randrange(2**32); genome=p.genome.mutate(rng) if w==0 or stagnation>=2 else p.genome
                jobs.append((f'g{gen}-{i}-{w}',p,arm,prompt,seed,genome))
        replies=await asyncio.gather(*(request(a,pr,s) for _,_,a,pr,s,_ in jobs))
        codes = []
        for (_,p,_,_,_,_),patch in zip(jobs,replies):
            try: codes.append(apply_patch(p.code,patch))
            except (ValueError,TypeError): codes.append(None)
        inputs = [EvaluationInput(code, tuple(cascade.challenge), cascade.grid)
                  for code in codes if code is not None]
        evaluated = iter(await evaluate_batch(inputs, executor))
        for (ident,p,arm,prompt,_,genome),patch,candidate in zip(jobs,replies,codes):
            attempts+=1
            if candidate is None:
                result=Result(0,reason='invalid patch'); code=''
            else:
                code=candidate
                output=next(evaluated)
                result=output.result
                for point in output.failed_points:
                    cascade.failures[point]+=1
            accepted=result.stage==3 and result.metrics[3]==1.
            if accepted:
                # A remote worker cannot send an unproved expression to the profiler.
                accepted=prove(code)['proved']
            if accepted and performance_policy is not None:
                record=performance.check_candidate(ident,code,result.metrics[0],result.metrics[1],p,archive,cascade.grid,performance_policy)
                perf_records.append(record)
                accepted=record['accepted']
                if not accepted: result=replace(result,reason='Stage 3 performance regression or profiling failure')
            if accepted:
                token=audit.issue(ident,code,result.metrics)
                accepted=audit.verify(token,ident,code,result.metrics)
            if accepted:
                archive.add(Artifact(ident,p.id,p.island,gen,code,genome,result.metrics))
                if score(result.metrics)>score(p.metrics):arm.wins+=1
            else: rejects+=1
            # Only retain parseable candidate patches, not arbitrary provider text.
            if code and result.stage>=2:buf.add(Trial(p.id,prompt,patch,score(result.metrics),score(p.metrics),accepted,VERSION))
        if gen%2==0:archive.migrate(gen)
        current=score(archive.best().metrics);stagnation=stagnation+1 if current<=best+1e-9 else 0;best=max(best,current)
        cascade.advance(cfg.seed+gen)
        stopped=not jobs
        with source_guard():
            if checkpoint is not None: checkpoint.save(gen,snapshot())
        if stopped:break
    champion=archive.best()
    report={'mode':'offline-simulation' if proposal is simulated_proposal else 'external-proposal-adapter','benchmark':VERSION,'baseline_score':score(baseline),'champion_score':score(champion.metrics),'champion':champion.code,'champion_metrics':champion.metrics,'champion_genome':champion.genome.__dict__,'holdout_quality':cascade.heldout(champion.code),'baseline_holdout_quality':cascade.heldout(BASELINE),'attempts':attempts,'rejections':rejects,'spent':router.spent,'budget_unit':'synthetic proposal credits (not USD)','lineage_size':len(archive.lineage),'occupied_cells':sum(len(c) for c in archive.cells),'model_pulls':{a.id:a.pulls for a in router.arms},'sft':[{'prompt':t.prompt,'completion':t.patch} for t in buf.sft],'dpo':buf.pairs()}

    report['formal_rule_count']=audit.rules.count
    if memory is not None:
        report.update(mode='memory-guided-offline',memory_contract=memory.contract(),release_authorized=False)
    if perf_context is not None:
        report['performance_regression']={'context':perf_context,'records':perf_records,'profiled':len(perf_records),'rejected':sum(not r['accepted'] for r in perf_records)}
    with source_guard(): return report
