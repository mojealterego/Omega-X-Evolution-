"""L12 v74: frozen campaign accounting and seed-paired statistical reporting.

Cardinality is not source reproduction. Caller supplies the reviewed manifest,
pinned digest and actual run records; this module never executes a candidate,
verifies referenced artifact bytes, or authorizes promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import random
import re

from .ontos_v72_jcs import canonical_json

_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z', re.ASCII)
_HEX = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_BOOTSTRAPS = 8192
_PERMUTATIONS = 8192


def _id(value: object) -> bool:
    return type(value) is str and _ID.fullmatch(value) is not None


def _hex(value: object) -> bool:
    return type(value) is str and _HEX.fullmatch(value) is not None


def _seed(value: object) -> bool:
    return type(value) is int and 0 <= value < 2**32


@dataclass(frozen=True, slots=True)
class Configuration:
    name: str
    suite: str
    group: str
    generation: str
    trials: int
    artifact_sha256: str

    def __post_init__(self) -> None:
        if (not _id(self.name) or type(self.suite) is not str or self.suite not in ('A','B','C','D')
                or type(self.group) is not str or self.group not in ('PRIMARY','ABLATION')
                or not _id(self.generation) or type(self.trials) is not int
                or not 1 <= self.trials <= 1_000_000 or not _hex(self.artifact_sha256)):
            raise ValueError('configuration contract')

    def body(self) -> dict:
        self.__post_init__()
        return {'name':self.name,'suite':self.suite,'group':self.group,
                'generation':self.generation,'trials':self.trials,
                'artifact_sha256':self.artifact_sha256}


@dataclass(frozen=True, slots=True)
class CampaignPlan:
    seeds: tuple[int, ...]
    configurations: tuple[Configuration, ...]
    comparisons: tuple[tuple[str,str], ...]
    analysis_seed: int
    protocol_sha256: str

    def __post_init__(self) -> None:
        if (type(self.seeds) is not tuple or len(self.seeds) != 30
                or not all(_seed(s) for s in self.seeds) or len(set(self.seeds)) != 30
                or type(self.configurations) is not tuple or len(self.configurations) != 60
                or any(type(c) is not Configuration for c in self.configurations)
                or not _seed(self.analysis_seed) or not _hex(self.protocol_sha256)
                or type(self.comparisons) is not tuple or not 1 <= len(self.comparisons) <= 60):
            raise ValueError('frozen campaign cardinality/seed contract')
        for c in self.configurations:
            c.__post_init__()
        configs = {c.name:c for c in self.configurations}
        if (len(configs) != 60 or sum(c.group=='PRIMARY' for c in configs.values()) != 36
                or {c.suite for c in configs.values()} != set('ABCD')):
            raise ValueError('expected 36 primary, 24 ablation and four suites')
        seen = set()
        for pair in self.comparisons:
            if (type(pair) is not tuple or len(pair)!=2 or not all(_id(x) for x in pair)
                    or pair[0]==pair[1] or any(x not in configs for x in pair)
                    or configs[pair[0]].suite != configs[pair[1]].suite
                    or frozenset(pair) in seen):
                raise ValueError('invalid or duplicate within-suite comparison')
            seen.add(frozenset(pair))

    def digest(self) -> str:
        self.__post_init__()
        return sha256(canonical_json({'schema':'omega-v74-campaign-v1',
            'seeds':list(self.seeds),'configurations':[c.body() for c in sorted(self.configurations,key=lambda c:c.name)],
            'comparisons':[list(p) for p in self.comparisons], 'analysis_seed':self.analysis_seed,
            'protocol_sha256':self.protocol_sha256,'bootstrap':_BOOTSTRAPS,'permutations':_PERMUTATIONS,
            'missing_policy':'zero-success-planned-denominator', 'alpha':.05,
            'ci':'Bonferroni percentile paired seed bootstrap','p':'two-sided paired sign flip Holm'})).hexdigest()


@dataclass(frozen=True, slots=True)
class Run:
    configuration: str
    seed: int
    status: str
    correct: int
    evidence_sha256: str

    def __post_init__(self) -> None:
        if (not _id(self.configuration) or not _seed(self.seed)
                or type(self.status) is not str or self.status not in ('COMPLETED','FAILED')
                or type(self.correct) is not int or not 0 <= self.correct <= 1_000_000
                or self.status=='FAILED' and self.correct!=0 or not _hex(self.evidence_sha256)):
            raise ValueError('run contract')


def paired_statistics(deltas: tuple[int, ...], denominator: int, *, seed: int,
                      family_size: int) -> dict:
    """Pair-level integer contrasts; bootstrap and sign flip assume independent seeds.

    Sign flip requires exchangeability under the null; intervals are approximate.
    Family-adjusted percentile intervals use Bonferroni, not a coverage proof.
    """
    if (type(denominator) is not int or not 1 <= denominator <= 10**12
            or type(deltas) is not tuple or not 2 <= len(deltas) <= 30
            or any(type(d) is not int or abs(d)>denominator for d in deltas)
            or not _seed(seed) or type(family_size) is not int or not 1 <= family_size <= 60):
        raise ValueError('paired analysis contract')
    rng = random.Random(seed)
    n = len(deltas)
    scale = n*denominator
    samples = sorted(sum(deltas[rng.randrange(n)] for _ in range(n)) for _ in range(_BOOTSTRAPS))
    tail = .025/family_size
    lower = samples[math.floor((_BOOTSTRAPS-1)*tail)]/scale
    upper = samples[math.ceil((_BOOTSTRAPS-1)*(1-tail))]/scale
    observed = abs(sum(deltas))
    def extreme(mask: int) -> bool:
        return abs(sum(d if mask & (1<<i) else -d for i,d in enumerate(deltas))) >= observed
    if n<=16:
        total=1<<n
        p=sum(extreme(mask) for mask in range(total))/total
        method='EXACT'
    else:
        total=_PERMUTATIONS
        p=(1+sum(extreme(rng.getrandbits(n)) for _ in range(total)))/(total+1)
        method='MONTE_CARLO_PLUS_ONE'
    return {'n':n,'mean_difference':sum(deltas)/scale,'ci_lower':lower,'ci_upper':upper,
            'ci_family_size':family_size,'bootstrap_resamples':_BOOTSTRAPS,
            'p_raw':p,'permutations':total,'permutation_method':method}


def holm_adjust(pvalues: tuple[float, ...]) -> tuple[float, ...]:
    if (type(pvalues) is not tuple or not 1 <= len(pvalues) <= 60
            or any(type(p) not in (float,int) or not math.isfinite(p) or not 0<=p<=1 for p in pvalues)):
        raise ValueError('p-value family contract')
    adjusted=[0.]*len(pvalues)
    previous=0.
    for rank,i in enumerate(sorted(range(len(pvalues)),key=lambda j:pvalues[j])):
        previous=max(previous,min(1.,(len(pvalues)-rank)*pvalues[i]))
        adjusted[i]=previous
    return tuple(adjusted)


def analyze_campaign(plan: CampaignPlan, pinned_digest: str, runs: tuple[Run, ...]) -> dict:
    if (type(plan) is not CampaignPlan or not _hex(pinned_digest) or plan.digest()!=pinned_digest
            or type(runs) is not tuple or len(runs)>1800):
        raise ValueError('campaign must match frozen plan and bounded records')
    configs={c.name:c for c in plan.configurations}
    seeds=set(plan.seeds)
    indexed={}
    for r in runs:
        if type(r) is not Run:
            raise ValueError('typed run required')
        r.__post_init__()
        key=(r.configuration,r.seed)
        if (r.configuration not in configs or r.seed not in seeds or key in indexed
                or r.correct>configs[r.configuration].trials):
            raise ValueError('unregistered, duplicate or invalid run')
        indexed[key]=r
    summaries={}
    generations={}
    def success(name,seed):
        row=indexed.get((name,seed))
        return row.correct if row is not None else 0
    for name,c in sorted(configs.items()):
        cohort=[indexed.get((name,s)) for s in plan.seeds]
        missing=sum(r is None for r in cohort)
        failed=sum(r is not None and r.status=='FAILED' for r in cohort)
        correct=sum(success(name,s) for s in plan.seeds)
        summaries[name]={'suite':c.suite,'group':c.group,'generation':c.generation,
            'planned_trials':30*c.trials,'correct':correct,'missing':missing,'failed':failed,
            'unconditional_success':correct/(30*c.trials)}
        group=generations.setdefault(c.generation,{'planned_runs':0,'missing':0,'failed':0})
        group['planned_runs']+=30; group['missing']+=missing; group['failed']+=failed
    comparisons=[]
    for i,(a,b) in enumerate(plan.comparisons):
        x,y=configs[a].trials,configs[b].trials
        d=tuple(success(a,s)*y-success(b,s)*x for s in plan.seeds)
        comparisons.append({'candidate':a,'baseline':b,**paired_statistics(d,x*y,
            seed=(plan.analysis_seed+i)%2**32,family_size=len(plan.comparisons))})
    for c,p in zip(comparisons,holm_adjust(tuple(c['p_raw'] for c in comparisons))):
        c['p_holm']=p
    records_sha=sha256(canonical_json([{'configuration':r.configuration,'seed':r.seed,
        'status':r.status,'correct':r.correct,'evidence_sha256':r.evidence_sha256}
        for _,r in sorted(indexed.items())])).hexdigest()
    return {'plan_sha256':pinned_digest,'records_sha256':records_sha,
        'planned':{'PRIMARY':1080,'ABLATION':720},'recorded':len(runs),'missing':1800-len(runs),
        'failed':sum(r.status=='FAILED' for r in runs),'all_runs_recorded':len(runs)==1800,
        'configurations':summaries,'generations':generations,'comparisons':comparisons,
        'source_reproduction_verified':False,'release_authorized':False}
