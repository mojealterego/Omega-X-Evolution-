"""Durable, fenced custody of one quarantined living-memory review.

Fixed genesis includes the complete signed evidence and candidate. Only signed
A-E extensions are appended; no replacement or reset across segment rollover.
Trust requires external genesis pin and retained fence, private directories,
and exclusive use of this gateway. No operational grants or physical custody.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import re

from .ontos_authenticated_boundary import BoundaryPlan, SignedEnvelope, replay_boundary
from .ontos_living_memory import Batch, review_candidate, review_session
from .ontos_managed_journal import Fence, ManagedJournal, ManagedSnapshot, ManagedUpdate
from .ontos_v51_sequential_memory import ReviewPlan, SignedTrial, review_family
from .ontos_v51_skepticism import MemoryEvent
from .ontos_v72_jcs import canonical_json, parse_json

_DOMAIN=b'OMEGA-X/living-journal/v1\x00'
_SHA=re.compile(r'[a-f0-9]{64}\Z')
MAX_TRIALS=64
MAX_MESSAGES=64
MAX_WIRE=2048
MAX_STATE=524288


def _pin(x):
    return type(x) is str and _SHA.fullmatch(x) is not None


def _trial(t):
    if type(t) is not SignedTrial or type(t.event) is not MemoryEvent:
        raise ValueError('typed trial required')
    e=t.event; e.__post_init__()
    if type(t.signature) is not bytes or len(t.signature)!=64:
        raise ValueError('trial signature shape')
    return [t.previous,t.sequence,t.signature.hex(),e.tenant,e.candidate_sha256,
            e.ident,e.group,e.source_sha256,e.positive,str(e.valid_from),
            str(e.valid_until),str(e.recorded_at)]


def _message(m):
    if (type(m) is not SignedEnvelope or not _pin(m.previous)
            or type(m.at_tick) is not int or not 0<=m.at_tick<2**63
            or type(m.raw) is not bytes or not 1<=len(m.raw)<=MAX_WIRE
            or type(m.signature) is not bytes or len(m.signature)!=64):
        raise ValueError('bounded signed message required')
    return [m.previous,str(m.at_tick),m.raw.hex(),m.signature.hex()]


def _read_message(row):
    a,b,c,d=row
    return SignedEnvelope(a,int(b),bytes.fromhex(c),bytes.fromhex(d))


@dataclass(frozen=True, slots=True)
class LivingGenesis:
    batch: Batch
    plan: ReviewPlan
    plan_pin: str
    trials: tuple[SignedTrial,...]
    evidence_head: str
    boundary: BoundaryPlan
    boundary_pin: str

    def _object(self):
        b,p,a=self.batch,self.plan,self.boundary
        if (type(b) is not Batch or type(p) is not ReviewPlan or type(a) is not BoundaryPlan
                or type(self.trials) is not tuple or len(self.trials)>MAX_TRIALS
                or not all(_pin(x) for x in (self.plan_pin,self.evidence_head,self.boundary_pin))):
            raise ValueError('bounded genesis required')
        b.__post_init__(); p.__post_init__(); a.__post_init__()
        return {'batch':[[[list(k),list(v)] for k,v in rows] for rows in (b.train,b.probes)],
                'plan':[p.tenant,list(p.candidates),p.evaluator_key.hex(),p.horizon,
                        p.alpha.numerator,p.alpha.denominator],
                'plan_pin':self.plan_pin,'trials':[_trial(t) for t in self.trials],
                'evidence_head':self.evidence_head,
                'boundary':[a.tenant,a.session_id,sorted(a.root_caps),a.deadline,
                            a.object_key.hex(),a.auditor_key.hex()],
                'boundary_pin':self.boundary_pin}

    @property
    def sha256(self):
        return sha256(_DOMAIN+b'genesis\x00'+canonical_json(self._object())).hexdigest()

    def validate(self):
        self._object()
        p,b,a=self.plan,self.batch,self.boundary
        if (b.sha256 not in p.candidates or a.tenant!=p.tenant
                or a.session_id!=review_session(self.plan_pin,self.evidence_head,b.sha256)
                or p.evaluator_key in (a.object_key,a.auditor_key)):
            raise ValueError('genesis scope mismatch')
        review_family(p,self.plan_pin,self.trials,expected_head=self.evidence_head)
        replay_boundary(a,self.boundary_pin,(),expected_head=self.boundary_pin)


def _read_genesis(obj):
    train,probes=obj['batch']; tenant,candidates,key,h,n,d=obj['plan']
    at,sid,caps,deadline,ok,ak=obj['boundary']
    trials=[]
    for row in obj['trials']:
        prev,seq,sig,t,c,i,g,s,pos,vf,vu,rec=row
        trials.append(SignedTrial(prev,seq,MemoryEvent(t,c,i,g,s,pos,int(vf),int(vu),int(rec)),bytes.fromhex(sig)))
    return LivingGenesis(Batch(tuple((tuple(k),tuple(v)) for k,v in train),tuple((tuple(k),tuple(v)) for k,v in probes)),
                         ReviewPlan(tenant,tuple(candidates),bytes.fromhex(key),h,Fraction(n,d)),
                         obj['plan_pin'],tuple(trials),obj['evidence_head'],
                         BoundaryPlan(at,sid,frozenset(caps),deadline,bytes.fromhex(ok),bytes.fromhex(ak)),obj['boundary_pin'])


@dataclass(frozen=True, slots=True)
class LivingState:
    genesis: LivingGenesis
    messages: tuple[SignedEnvelope,...]=()


class LivingJournal:
    """One pinned review session. Exact fences are mandatory for diagnostics."""
    def __init__(self, anchor: Path, segments: Path, genesis_pin: str):
        if not _pin(genesis_pin):
            raise ValueError('independent genesis pin required')
        self._pin=genesis_pin
        self._journal=ManagedJournal(anchor,segments,self._digest,self._replay,self._encode,self._decode)

    def _encode(self,state: LivingState) -> bytes:
        if (type(state) is not LivingState or type(state.genesis) is not LivingGenesis
                or state.genesis.sha256!=self._pin or type(state.messages) is not tuple
                or len(state.messages)>MAX_MESSAGES):
            raise ValueError('pinned state bounds')
        raw=canonical_json({'genesis':state.genesis._object(),'messages':[_message(m) for m in state.messages]})
        if len(raw)>MAX_STATE: raise ValueError('state byte budget')
        return raw

    def _decode(self,raw: bytes) -> LivingState:
        if type(raw) is not bytes or not 1<=len(raw)<=MAX_STATE:
            raise ValueError('state byte budget')
        try:
            obj=parse_json(raw)
            state=LivingState(_read_genesis(obj['genesis']),tuple(_read_message(m) for m in obj['messages']))
            if self._encode(state)!=raw: raise ValueError('noncanonical state')
            return state
        except (TypeError,KeyError,AttributeError,OverflowError,ZeroDivisionError) as exc:
            raise ValueError('invalid state schema') from exc

    def _digest(self,state: LivingState) -> bytes:
        return sha256(_DOMAIN+b'state\x00'+self._encode(state)).digest()

    def _replay(self,state: LivingState,payload: bytes) -> LivingState | None:
        if len(state.messages)>=MAX_MESSAGES: return None
        try:
            m=_read_message(parse_json(payload))
            if canonical_json(_message(m))!=payload: return None
            successor=replace(state,messages=state.messages+(m,))
            g=state.genesis
            replay_boundary(g.boundary,g.boundary_pin,successor.messages)
            return successor
        except (ValueError,TypeError,AttributeError,KeyError,OverflowError):
            return None

    def initialize(self,genesis: LivingGenesis) -> ManagedSnapshot[LivingState]:
        if type(genesis) is not LivingGenesis or genesis.sha256!=self._pin:
            raise ValueError('genesis pin mismatch')
        genesis.validate()
        return self._journal.initialize(LivingState(genesis))

    def read(self,retained: Fence) -> ManagedSnapshot[LivingState]:
        if type(retained) is not Fence: raise ValueError('exact retained fence required')
        return self._journal.read(retained)

    def recover_from_anchor(self) -> ManagedSnapshot[LivingState]:
        """Explicitly trust protected anchor; does not prove anti-rollback."""
        return self._journal.read()

    def append(self,expected: Fence,message: SignedEnvelope) -> ManagedUpdate[LivingState]:
        return self._journal.append(expected,canonical_json(_message(message)))

    def compact(self,expected: Fence) -> ManagedUpdate[LivingState]:
        return self._journal.compact(expected)

    def verify_sealed(self,generation: int) -> ManagedSnapshot[LivingState]:
        return self._journal.verify_sealed(generation)

    def diagnostic(self,retained: Fence) -> dict:
        """Historical snapshot diagnostic; not a live authorization lease."""
        s=self.read(retained).state; g=s.genesis
        head=s.messages[-1].sha256(g.boundary_pin) if s.messages else g.boundary_pin
        if len(s.messages)>=MAX_MESSAGES:
            return {'decision':'QUARANTINED_BLOCKED','reason':'TRANSCRIPT_EXHAUSTED',
                    'candidate_sha256':g.batch.sha256,'evidence_head':g.evidence_head,
                    'boundary_head':head,'diagnostic':None,'null_verified':False,
                    'promotion_authorized':False}
        return review_candidate(g.batch,g.plan,g.plan_pin,g.trials,g.evidence_head,
                                g.boundary,g.boundary_pin,s.messages,head)
