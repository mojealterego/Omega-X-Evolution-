"""Versioned, signed eight-axis R0/R1 projection over the fenced journal.

The operator supplies a trusted monotonic clock and independently retained fence.
No external IAM, physical deletion, or automatic promotion. Legacy RCC journals
remain separate; migration must preserve revocations and provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from functools import lru_cache

from .ontos_managed_journal import Fence, ManagedJournal
from .ontos_epoch_journal_core import IntegrityError
from .ontos_rcc import Statistics, _name, _pin, _int
from .ontos_v72_jcs import canonical_json, parse_json
from .ontos_v72_receipts import strict_verify

DOMAIN=b'OMEGA-X/OTCE/v1\x00'
MAX_NODES=16
MAX_ROTATIONS=8
MAX_EVENTS=2*MAX_NODES+MAX_ROTATIONS
MAX_TIME=2**31-1


def _digest(tag, value):
    return sha256(DOMAIN+tag+b'\x00'+canonical_json(value)).hexdigest()


def _key(k): return type(k) is bytes and len(k)==32


def _time(t): return _int(t,0,MAX_TIME)


@dataclass(frozen=True, slots=True)
class Scope:
    tenant: str
    encoder: str
    evolution: int
    dimension: int
    writer: bytes
    revoker: bytes
    reader: bytes

    def __post_init__(self):
        keys=(self.writer,self.revoker,self.reader)
        if (not _name(self.tenant) or not _pin(self.encoder) or not _int(self.evolution,1,MAX_TIME)
                or not _int(self.dimension,1,8) or not all(_key(k) for k in keys) or len(set(keys))!=3):
            raise ValueError('invalid scope')

    @property
    def pin(self):
        self.__post_init__()
        return _digest(b'scope',[self.tenant,self.encoder,self.evolution,self.dimension,
                                 self.writer.hex(),self.revoker.hex(),self.reader.hex()])


@dataclass(frozen=True, slots=True)
class Coordinates:
    start: int
    end: int
    cognitive: int
    causal: int
    observed: int
    forecast: int | None
    evolution: int
    expires: int

    def __post_init__(self):
        if (not all(_time(t) for t in (self.start,self.end,self.cognitive,self.causal,self.observed,self.expires))
                or not self.start<self.end or not self.observed<self.expires
                or not _int(self.evolution,1,MAX_TIME)
                or (self.forecast is not None and (not _time(self.forecast) or self.forecast<self.observed))):
            raise ValueError('invalid coordinates')


@dataclass(frozen=True, slots=True)
class Query:
    branch: str
    valid: int
    known: int
    cognitive: int
    causal: int
    observed: int
    evolution: int
    forecast: int | None

    def __post_init__(self):
        if (not _name(self.branch) or not all(_time(t) for t in (self.valid,self.cognitive,self.causal,self.observed))
                or not _int(self.known,0,MAX_EVENTS) or not _int(self.evolution,1,MAX_TIME)
                or (self.branch=='actual')!=(self.forecast is None)
                or (self.forecast is not None and not _time(self.forecast))):
            raise ValueError('invalid query')


@dataclass(frozen=True, slots=True)
class Event:
    previous: str
    sequence: int
    kind: str
    body: bytes
    signature: bytes

    def wire(self):
        if (not _pin(self.previous) or not _int(self.sequence,1,MAX_EVENTS)
                or type(self.kind) is not str or self.kind not in ('put','revoke','rotate','migrate')
                or type(self.body) is not bytes or not 1<=len(self.body)<=2048
                or type(self.signature) is not bytes or len(self.signature)!=64):
            raise ValueError('invalid event')
        return canonical_json([self.previous,self.sequence,self.kind,self.body.hex(),self.signature.hex()])


def event_bytes(scope,event):
    event.wire()
    return DOMAIN+b'event\x00'+canonical_json([scope.pin,event.previous,event.sequence,event.kind,event.body.hex()])


def _event(raw):
    p,s,k,b,g=parse_json(raw)
    e=Event(p,s,k,bytes.fromhex(b),bytes.fromhex(g))
    if e.wire()!=raw: raise ValueError('noncanonical event')
    return e


@dataclass(frozen=True, slots=True)
class Read:
    fence: Fence
    epoch: int
    operation: str
    key: str
    query: Query
    issued: int
    expires: int
    signature: bytes


def read_bytes(scope,r):
    if (type(r) is not Read or type(r.fence) is not Fence or type(r.query) is not Query
            or not _int(r.epoch,1,MAX_ROTATIONS+1) or type(r.operation) is not str
            or r.operation not in ('recall','weights','explain') or not _name(r.key)
            or not _time(r.issued) or not _time(r.expires) or not 0<r.expires-r.issued<=64
            or type(r.signature) is not bytes or len(r.signature)!=64):
        raise ValueError('invalid read')
    r.fence.__post_init__(); r.query.__post_init__()
    f=r.fence
    return DOMAIN+b'read\x00'+canonical_json([scope.pin,[f.generation,f.cursor.sequence,
        f.cursor.digest.hex(),f.lineage.hex()],r.epoch,r.operation,r.key,asdict(r.query),r.issued,r.expires])


def _reduce(scope,events,*,verify=None,payload_check=None,event_preimage=event_bytes):
    nodes={}; revoked=set(); reader=scope.reader; retired={reader,scope.writer,scope.revoker}; epoch=1; head=scope.pin
    evolution=scope.evolution; migrated_at=0
    for seq,raw in enumerate(events,1):
        e=_event(raw); b=parse_json(e.body)
        if e.previous!=head or e.sequence!=seq or type(b) is not dict or canonical_json(b)!=e.body:
            raise ValueError('invalid event chain')
        if verify is not None and not verify(scope.writer if e.kind=='put' else scope.revoker,event_preimage(scope,e),e.signature):
            raise ValueError('invalid event signature')
        if e.kind in ('rotate','migrate'):
            fields={'epoch','reader'}
            if e.kind=='migrate':
                fields.update(('evolution','encoder'))
                if (not _int(b.get('evolution'),1,MAX_TIME) or b['evolution']!=evolution+1
                        or b.get('encoder')!=scope.encoder):
                    raise ValueError('migration requires next evolution and unchanged encoder')
            if set(b)!=fields or not _int(b['epoch'],2,MAX_ROTATIONS+1) or b['epoch']!=epoch+1 or not _pin(b['reader']):
                raise ValueError('invalid policy rotation')
            reader=bytes.fromhex(b['reader'])
            if reader in retired: raise ValueError('reused role key')
            retired.add(reader); epoch=b['epoch']
            if e.kind=='migrate':
                evolution=b['evolution']; migrated_at=seq
        elif e.kind=='revoke':
            if set(b)!={'id'} or not _name(b['id']) or b['id'] not in nodes or b['id'] in revoked:
                raise ValueError('invalid revoke')
            affected={b['id']}
            for i,n in nodes.items():
                if affected.intersection(n['parents']): affected.add(i)
            revoked.update(affected)
        else:
            if set(b)!={'id','parents','kind','evidence','branch','time','source','payload'}:
                raise ValueError('invalid capsule schema')
            i,parents=b['id'],b['parents']; kind=b['kind']; evidence=b['evidence']; branch=b['branch']
            if (not _name(i) or i in nodes or len(nodes)>=MAX_NODES or type(parents) is not list or len(parents)>8
                    or any(not _name(p) or p not in nodes or p in revoked for p in parents) or len(set(parents))!=len(parents)
                    or kind not in ('R0','R1') or evidence not in ('observed','inferred','simulated','disputed')
                    or not _name(branch) or not _pin(b['source']) or type(b['time']) is not dict or type(b['payload']) is not dict):
                raise ValueError('invalid capsule')
            t=Coordinates(**b['time']); ancestry=[nodes[p] for p in parents]
            if (t.evolution!=evolution or t.causal!=max((p['time']['causal']+1 for p in ancestry),default=0)
                    or any(t.cognitive<p['time']['cognitive'] or t.observed<p['time']['observed'] for p in ancestry)
                    or (branch=='actual')!=(t.forecast is None) or (branch!='actual')!=(evidence=='simulated')
                    or any(p['branch'] not in ('actual',branch) for p in ancestry)
                    or (evidence=='observed' and any(p['evidence']!='observed' for p in ancestry))):
                raise ValueError('invalid causal or temporal lineage')
            payload=b['payload']
            if payload_check is not None:
                if kind=='R1' and (evidence!='observed' or not parents):
                    raise ValueError('invalid R1 lineage')
                payload_check(b)
            elif kind=='R0':
                if set(payload)!={'key','value'} or not _name(payload['key']) or type(payload['value']) is not str or len(payload['value'])>512:
                    raise ValueError('invalid R0 payload')
            else:
                if evidence!='observed' or not parents or set(payload)!={'x','y'} or type(payload['x']) is not list:
                    raise ValueError('invalid R1 payload')
                Statistics.zero(scope.dimension).delta(tuple(payload['x']),payload['y'],1)
            b['transaction']=seq; b['policy_epoch']=epoch; b['operator']='projection-v1' if kind=='R0' else 'ridge-v1'
            b['input']=_digest(b'input',[scope.encoder,b['source'],[p['output'] for p in ancestry]])
            b['output']=_digest(b'output',b)
            nodes[i]=b
        head=_digest(b'head',[scope.pin,raw.hex()])
    return nodes,revoked,reader,epoch,head,evolution,migrated_at


@dataclass(frozen=True, slots=True)
class Result:
    status: str
    fence: Fence | None
    head: str | None
    count: int | None


class OTCEJournal:
    def __init__(self,anchor,segments,scope: Scope,pin: str):
        if type(scope) is not Scope or scope.pin!=pin: raise ValueError('independent scope pin required')
        self._scope=scope
        # Cache only the pure cryptographic predicate, not state or authorization.
        # Exact immutable key/message/signature tuple; bounded and cold on reopen.
        self._verify_event=lru_cache(maxsize=128)(strict_verify)
        self._journal=ManagedJournal(anchor,segments,self._hash,self._replay,self._encode,self._decode)

    def _state_pin(self): return self._scope.pin

    def _event_bytes(self,e): return event_bytes(self._scope,e)

    def _reduce(self,events,*,verify=None):
        return _reduce(self._scope,events,verify=verify)

    def _encode(self,events):
        if type(events) is not tuple or len(events)>MAX_EVENTS: raise ValueError('event budget')
        return canonical_json([self._state_pin(),[r.hex() for r in events]])

    def _hash(self,events): return sha256(DOMAIN+b'state\x00'+self._encode(events)).digest()

    def _decode(self,raw):
        try:
            pin,rows=parse_json(raw)
            if pin!=self._state_pin() or type(rows) is not list or len(rows)>MAX_EVENTS: raise ValueError('scope')
            events=tuple(bytes.fromhex(r) for r in rows)
            if self._encode(events)!=raw: raise ValueError('noncanonical state')
            self._reduce(events,verify=self._verify_event)
            return events
        except (TypeError,KeyError,AttributeError,OverflowError) as exc: raise ValueError('invalid state') from exc

    def _replay(self,events,raw):
        if len(events)>=MAX_EVENTS: return None
        try:
            e=_event(raw)
            if not self._verify_event(self._scope.writer if e.kind=='put' else self._scope.revoker,self._event_bytes(e),e.signature): return None
            out=events+(raw,); self._reduce(out); return out
        except (ValueError,TypeError,KeyError,AttributeError,OverflowError): return None

    def _result(self,status,snapshot):
        if status not in ('INITIALIZED','COMMITTED','COMPACTED','RECOVERED'): return Result(status,None,None,None)
        return Result(status,snapshot.fence,self._reduce(snapshot.state)[4],len(snapshot.state))

    def initialize(self): return self._result('INITIALIZED',self._journal.initialize(()))

    def recover_from_anchor(self):
        """Explicit trust in protected anchor; not proof of freshness."""
        return self._result('RECOVERED',self._journal.read())

    def append(self,expected,e):
        if type(e) is not Event: raise ValueError('typed event required')
        u=self._journal.append(expected,e.wire()); return self._result(u.status,u.snapshot)

    def compact(self,expected):
        u=self._journal.compact(expected); return self._result(u.status,u.snapshot)

    def _selection(self,r: Read,*,retained: Fence,now: int):
        preimage=read_bytes(self._scope,r)
        if not _time(now) or not r.issued<=now<r.expires: raise ValueError('read outside trusted clock interval')
        if type(retained) is not Fence: raise ValueError('independently retained fence required')
        if r.fence!=retained: raise IntegrityError('request differs from independently retained fence')
        snap=self._journal.read(retained)
        nodes,revoked,reader,epoch,_,evolution,migrated_at=self._reduce(snap.state)
        if r.epoch!=epoch or not strict_verify(reader,preimage,r.signature): raise ValueError('read authorization')
        q=r.query; visible={}; selected=[]
        for i,n in nodes.items():
            t=n['time']
            if (i in revoked or not now<t['expires'] or t['observed']>min(q.observed,now)
                    or n['transaction']>q.known or t['cognitive']>q.cognitive or t['causal']>q.causal
                    or q.evolution!=evolution or q.known<migrated_at or any(p not in visible for p in n['parents'])
                    or (n['branch']!='actual' and (n['branch']!=q.branch or t['forecast']!=q.forecast))): continue
            visible[i]=n
            if n['branch']==q.branch and t['start']<=q.valid<t['end']: selected.append(n)
        return selected,evolution

    def read(self,r: Read,*,retained: Fence,now: int):
        selected,evolution=self._selection(r,retained=retained,now=now)
        q=r.query
        if r.operation=='recall':
            for n in reversed(selected):
                if n['kind']=='R0' and n['evidence']==('observed' if q.branch=='actual' else 'simulated') and n['payload']['key']==r.key:
                    return n['payload']['value']
            return None
        if r.operation=='weights':
            if q.branch!='actual': raise ValueError('no simulated training')
            stats=Statistics.zero(self._scope.dimension)
            for n in selected:
                if n['kind']=='R1': stats=stats.delta(tuple(n['payload']['x']),n['payload']['y'],1)
            return stats.ridge(1)
        return [{**{k:v for k,v in n.items() if k!='payload'}, 'view_evolution':evolution} for n in selected]
