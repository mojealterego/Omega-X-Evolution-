"""Bounded associative/predictive memory research kernel, not trained Titans/JEPA.

Three adaptive scales, modern Hopfield readout, bipolar VSA, and linear latent
prediction. Only offline diagnostics; no operational memory write or grant.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

import numpy as np

from .ontos_authenticated_boundary import BoundaryPlan, SignedEnvelope, replay_boundary
from .ontos_v51_sequential_memory import ReviewPlan, SignedTrial, review_family
from .ontos_v72_jcs import canonical_json

_DOMAIN = b'OMEGA-X/living-memory/v1\x00'
_HEX = re.compile(r'[0-9a-f]{64}\Z')
_SCALES = ((.5,.4),(.2,.7),(.05,.9))


def _vector(v):
    return (type(v) is tuple and 8 <= len(v) <= 64
            and all(type(x) is int and x in (-1,1) for x in v))


def bind(a, b):
    """Bipolar VSA binding is its own inverse for a fixed key."""
    if not _vector(a) or not _vector(b) or len(a)!=len(b):
        raise ValueError('bounded bipolar vectors required')
    return tuple(x*y for x,y in zip(a,b))


@dataclass(frozen=True, slots=True)
class Batch:
    train: tuple[tuple[tuple[int,...],tuple[int,...]],...]
    probes: tuple[tuple[tuple[int,...],tuple[int,...]],...]

    def __post_init__(self):
        if (type(self.train) is not tuple or not 1<=len(self.train)<=64
                or type(self.probes) is not tuple or not 1<=len(self.probes)<=32):
            raise ValueError('bounded training and probe batches required')
        rows=self.train+self.probes
        if any(type(row) is not tuple or len(row)!=2 or not all(_vector(v) for v in row) for row in rows):
            raise ValueError('invalid memory pair')
        d=len(rows[0][0])
        if any(len(v)!=d for row in rows for v in row):
            raise ValueError('inconsistent latent dimension')
        if {k for k,_ in self.train}&{k for k,_ in self.probes}:
            raise ValueError('exact training/probe key overlap')

    @property
    def sha256(self):
        self.__post_init__()
        data={'train':[[list(k),list(v)] for k,v in self.train],
              'probes':[[list(k),list(v)] for k,v in self.probes]}
        return hashlib.sha256(_DOMAIN+b'batch\x00'+canonical_json(data)).hexdigest()


def diagnose(batch: Batch) -> dict:
    """Train on train only; probes are read-only. Fixed algorithm and bounds.

    Normalized residual outer products, surprise-scaled learning, momentum,
    Frobenius norm clipping, three rates. Hopfield softmax is over training
    keys, with VSA-bound values decoded per stored key. This is a finite
    linear predictive surrogate, not a neural implementation of the papers.
    """
    if type(batch) is not Batch:
        raise ValueError('batch required')
    batch.__post_init__()
    d=len(batch.train[0][0]); weights=np.zeros((3,d,d)); momentum=np.zeros_like(weights)
    for key,value in batch.train:
        x=np.asarray(key,dtype=np.float64); y=np.asarray(value,dtype=np.float64)
        for i,(rate,decay) in enumerate(_SCALES):
            residual=y-weights[i]@x
            surprise=min(1.,float(np.linalg.norm(residual))/np.sqrt(d))
            gradient=np.outer(residual,x)/d
            momentum[i]=decay*momentum[i]+(1-decay)*gradient
            weights[i]+=rate*surprise*momentum[i]
            norm=float(np.linalg.norm(weights[i]))
            if norm>2.: weights[i]*=2./norm
    keys=np.asarray([k for k,_ in batch.train],dtype=np.float64)
    values=np.asarray([bind(bind(k,v),k) for k,v in batch.train],dtype=np.float64)
    predictions=[]; target=[]; recalled=[]
    for k,v in batch.probes:
        x=np.asarray(k,dtype=np.float64)
        logits=8.*(keys@x)/d
        att=np.exp(logits-np.max(logits)); att/=np.sum(att)
        recalled.append(att@values)
        predictions.append(np.clip(np.mean(weights@x,axis=0),-1.,1.))
        target.append(v)
    pred=np.asarray(predictions); truth=np.asarray(target); rec=np.asarray(recalled)
    def accuracy(y):
        return float(np.mean(np.sign(y)==truth))
    return {'model_sha256':hashlib.sha256(weights.astype('<f8').tobytes()).hexdigest(),
            'scale_weight_norms':tuple(float(np.linalg.norm(w)) for w in weights),
            'predictions':tuple(tuple(map(float,row)) for row in pred),
            'predictive_mse':float(np.mean((pred-truth)**2)),
            'zero_predictor_mse':float(np.mean(truth**2)),
            'predictive_bit_accuracy':accuracy(pred),'hopfield_bit_accuracy':accuracy(rec),
            'promotion_authorized':False}


def review_session(plan_pin: str, evidence_head: str, candidate: str) -> str:
    if any(type(x) is not str or _HEX.fullmatch(x) is None for x in (plan_pin,evidence_head,candidate)):
        raise ValueError('exact SHA256 pins required')
    return hashlib.sha256(_DOMAIN+b'session\x00'+b''.join(bytes.fromhex(x) for x in (plan_pin,evidence_head,candidate))).hexdigest()


def review_candidate(batch: Batch, plan: ReviewPlan, plan_pin: str,
                     trials: tuple[SignedTrial,...], evidence_head: str,
                     boundary: BoundaryPlan, boundary_pin: str,
                     messages: tuple[SignedEnvelope,...], boundary_head: str) -> dict:
    """Replay both independent histories before a quarantined diagnostic.

    Both exact heads and genesis pins must come from trusted external custody;
    freshness and the statistical null are not proven. The A-E session binds
    this particular candidate and evidence head. No promotion on any path.
    """
    if type(batch) is not Batch or type(plan) is not ReviewPlan or type(boundary) is not BoundaryPlan:
        raise ValueError('typed plans and batch required')
    candidate=batch.sha256
    session=review_session(plan_pin,evidence_head,candidate)
    if (type(boundary_head) is not str or _HEX.fullmatch(boundary_head) is None
            or candidate not in plan.candidates or boundary.tenant!=plan.tenant
            or boundary.session_id!=session
            or plan.evaluator_key in (boundary.object_key,boundary.auditor_key)):
        raise ValueError('candidate, tenant, role or history binding mismatch')
    family=review_family(plan,plan_pin,trials,expected_head=evidence_head)
    control=replay_boundary(boundary,boundary_pin,messages,expected_head=boundary_head)
    selected=next(c for c in family.candidates if c.candidate_sha256==candidate)
    allowed=(selected.status=='REVIEW_THRESHOLD' and control.session.phase=='MODEL_APPROVED'
             and 'remember' in control.session.caps)
    return {'decision':'QUARANTINED_DIAGNOSTIC' if allowed else 'QUARANTINED_BLOCKED',
            'candidate_sha256':candidate,'evidence_head':family.head,'boundary_head':control.head,
            'diagnostic':diagnose(batch) if allowed else None,
            'null_verified':False,'promotion_authorized':False}
