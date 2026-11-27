"""Bounded signed RCC R0/R1 journal; logical revocation, not physical erasure.

One independently pinned tenant/encoder/epoch per journal. Trusted local caller
must retain the newest fence and authorize reads. No model promotion or R2-R4
execution; source commitments authenticate claims, not factual truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import re

from .ontos_managed_journal import Fence, ManagedJournal
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_receipts import strict_verify

DOMAIN=b'OMEGA-X/RCC/v1\x00'
MAX_EVENTS=32
MAX_NODES=16  # Reserve one revocation command per admitted node.
MAX_BODY=2048
_NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
_SHA=re.compile(r'[0-9a-f]{64}\Z')


def _name(x): return type(x) is str and _NAME.fullmatch(x) is not None

def _pin(x): return type(x) is str and _SHA.fullmatch(x) is not None

def _int(x,lo,hi): return type(x) is int and lo<=x<=hi


@dataclass(frozen=True,slots=True)
class Plan:
    tenant: str
    encoder: str
    epoch: int
    dimension: int
    writer: bytes
    revoker: bytes

    def __post_init__(self):
        if (not _name(self.tenant) or not _pin(self.encoder) or not _int(self.epoch,1,2**31-1)
                or not _int(self.dimension,1,8) or self.writer==self.revoker
                or any(type(k) is not bytes or len(k)!=32 for k in (self.writer,self.revoker))):
            raise ValueError('invalid RCC scope')

    @property
    def pin(self):
        self.__post_init__()
        return sha256(DOMAIN+canonical_json([self.tenant,self.encoder,self.epoch,self.dimension,
                                            self.writer.hex(),self.revoker.hex()])).hexdigest()


@dataclass(frozen=True,slots=True)
class Command:
    previous: str
    sequence: int
    kind: str
    body: bytes
    signature: bytes

    def wire(self):
        if (not _pin(self.previous) or not _int(self.sequence,1,MAX_EVENTS)
                or self.kind not in ('atom','learn','revoke') or type(self.kind) is not str
                or type(self.body) is not bytes or not 1<=len(self.body)<=MAX_BODY
                or type(self.signature) is not bytes or len(self.signature)!=64):
            raise ValueError('invalid RCC command')
        return canonical_json([self.previous,self.sequence,self.kind,self.body.hex(),self.signature.hex()])

    def head(self,plan): return sha256(DOMAIN+b'event\x00'+bytes.fromhex(plan.pin)+self.wire()).hexdigest()


def signing_bytes(plan: Plan,c: Command):
    c.wire()
    return DOMAIN+b'sign\x00'+canonical_json([plan.pin,c.previous,c.sequence,c.kind,c.body.hex()])


def _read(raw):
    a,b,c,d,e=parse_json(raw)
    cmd=Command(a,b,c,bytes.fromhex(d),bytes.fromhex(e))
    if cmd.wire()!=raw: raise ValueError('noncanonical command')
    return cmd


@dataclass(frozen=True,slots=True)
class Statistics:
    n: int
    a: tuple[tuple[int,...],...]
    b: tuple[int,...]

    @classmethod
    def zero(cls,d):
        if not _int(d,1,8): raise ValueError('dimension')
        return cls(0,tuple((0,)*d for _ in range(d)),(0,)*d)

    def delta(self,x,y,sign):
        d=len(self.b)
        if (type(x) is not tuple or len(x)!=d or any(not _int(v,-10**6,10**6) for v in x)
                or not _int(y,-10**6,10**6) or type(sign) is not int or sign not in (-1,1)
                or not 0<=self.n+sign<=MAX_EVENTS): raise ValueError('invalid contribution')
        return Statistics(self.n+sign,tuple(tuple(self.a[i][j]+sign*x[i]*x[j] for j in range(d)) for i in range(d)),
                          tuple(self.b[i]+sign*x[i]*y for i in range(d)))

    def ridge(self,lam):
        if not _int(lam,1,10**6): raise ValueError('ridge penalty')
        d=len(self.b)
        m=[[Fraction(self.a[i][j]+(lam if i==j else 0)) for j in range(d)]+[Fraction(self.b[i])] for i in range(d)]
        for i in range(d):
            pivot=m[i][i]
            if pivot<=0: raise ValueError('nonpositive ridge pivot')
            m[i]=[v/pivot for v in m[i]]
            for k in range(d):
                if k!=i:
                    z=m[k][i]; m[k]=[v-z*u for v,u in zip(m[k],m[i])]
        return tuple(row[-1] for row in m)


def _materialize(plan,events):
    nodes={}; revoked=set(); eligible=set(); stats=Statistics.zero(plan.dimension); head=plan.pin
    for seq,raw in enumerate(events,1):
        c=_read(raw); b=parse_json(c.body)
        if c.previous!=head or c.sequence!=seq or type(b) is not dict or canonical_json(b)!=c.body:
            raise ValueError('command chain or body')
        ident=b.get('id')
        if not _name(ident): raise ValueError('identifier')
        if c.kind=='revoke':
            if set(b)!={'id'} or ident not in nodes or ident in revoked: raise ValueError('unknown or revoked root')
            # Insertion order is topological; each affected contribution is removed once.
            affected={ident}
            for i,(_,_,node) in nodes.items():
                if affected.intersection(node['parents']): affected.add(i)
            for i in affected-revoked:
                kind,_,node=nodes[i]
                if kind=='learn': stats=stats.delta(tuple(node['x']),node['y'],-1)
            revoked.update(affected)
        else:
            parents=b.get('parents')
            if (len(nodes)>=MAX_NODES or ident in nodes or type(parents) is not list or len(parents)>8
                    or any(not _name(p) or p not in nodes or p in revoked for p in parents)
                    or len(set(parents))!=len(parents)):
                raise ValueError('invalid lineage')
            if c.kind=='atom':
                if (set(b)!={'id','key','value','start','end','source','parents','evidence'} or not _name(b['key'])
                        or type(b['value']) is not str or len(b['value'])>512 or not _pin(b['source'])
                        or not _int(b['start'],0,2**31-1) or not _int(b['end'],1,2**31-1)
                        or b['start']>=b['end'] or type(b['evidence']) is not str
                        or b['evidence'] not in ('observed','inferred','simulated','disputed')):
                    raise ValueError('invalid atom')
                if b['evidence']=='observed':
                    if any(p not in eligible for p in parents): raise ValueError('unobserved lineage')
                    eligible.add(ident)
            else:
                if set(b)!={'id','parents','x','y'} or not parents or type(b['x']) is not list or any(p not in eligible for p in parents):
                    raise ValueError('invalid R1 capsule')
                stats=stats.delta(tuple(b['x']),b['y'],1)
                eligible.add(ident)
            nodes[ident]=(c.kind,seq,b)
        head=c.head(plan)
    # Independent active-set recomputation guards against duplicate downdates.
    check=Statistics.zero(plan.dimension)
    for i,(kind,_,node) in nodes.items():
        if kind=='learn' and i not in revoked: check=check.delta(tuple(node['x']),node['y'],1)
    if check!=stats: raise ValueError('R1 invariant')
    return nodes,revoked,stats,head


@dataclass(frozen=True,slots=True)
class Result:
    status: str
    fence: Fence | None
    head: str | None
    count: int | None


class RCCJournal:
    """Bounded R0 atom projection and R1 capsule; no general model unlearning."""
    def __init__(self,anchor: Path,segments: Path,plan: Plan,pin: str):
        if type(plan) is not Plan or plan.pin!=pin: raise ValueError('independent plan pin required')
        self._plan=plan
        self._journal=ManagedJournal(anchor,segments,self._digest,self._replay,self._encode,self._decode)

    def _encode(self,events):
        if type(events) is not tuple or len(events)>MAX_EVENTS: raise ValueError('RCC horizon')
        return canonical_json([self._plan.pin,[raw.hex() for raw in events]])

    def _decode(self,raw):
        try:
            pin,rows=parse_json(raw)
            if pin!=self._plan.pin or type(rows) is not list or len(rows)>MAX_EVENTS: raise ValueError('scope')
            events=tuple(bytes.fromhex(x) for x in rows)
            if self._encode(events)!=raw: raise ValueError('noncanonical state')
            _materialize(self._plan,events)
            return events
        except (TypeError,KeyError,AttributeError,OverflowError) as exc:
            raise ValueError('invalid RCC state') from exc

    def _digest(self,events): return sha256(DOMAIN+b'state\x00'+self._encode(events)).digest()

    def _replay(self,events,raw):
        if len(events)>=MAX_EVENTS: return None
        try:
            c=_read(raw); key=self._plan.revoker if c.kind=='revoke' else self._plan.writer
            if not strict_verify(key,signing_bytes(self._plan,c),c.signature): return None
            successor=events+(raw,); _materialize(self._plan,successor)
            return successor
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError): return None

    def _result(self,status,snapshot):
        if status not in ('INITIALIZED','RECOVERED','COMMITTED','COMPACTED'): return Result(status,None,None,None)
        events=snapshot.state
        return Result(status,snapshot.fence,_materialize(self._plan,events)[3],len(events))

    def initialize(self): return self._result('INITIALIZED',self._journal.initialize(()))

    def recover_from_anchor(self):
        """Explicit operator recovery; protected anchor trust is not freshness proof."""
        return self._result('RECOVERED',self._journal.read())

    def append(self,expected: Fence,c: Command):
        if type(c) is not Command: raise ValueError('typed command required')
        u=self._journal.append(expected,c.wire()); return self._result(u.status,u.snapshot)

    def compact(self,expected: Fence):
        u=self._journal.compact(expected); return self._result(u.status,u.snapshot)

    def _view(self,retained: Fence):
        if type(retained) is not Fence: raise ValueError('exact retained fence required')
        return _materialize(self._plan,self._journal.read(retained).state)

    def statistics(self,retained: Fence): return self._view(retained)[2]

    def weights(self,retained: Fence,lam: int=1): return self.statistics(retained).ridge(lam)

    def recall(self,retained: Fence,key: str,valid: int,known: int):
        if not _name(key) or not _int(valid,0,2**31-1) or not _int(known,0,MAX_EVENTS): raise ValueError('query')
        nodes,revoked,_,_=self._view(retained)
        for ident,(kind,seq,b) in reversed(tuple(nodes.items())):
            if ident not in revoked and kind=='atom' and b['evidence']=='observed' and seq<=known and b['key']==key and b['start']<=valid<b['end']:
                return b['value']
        return None
