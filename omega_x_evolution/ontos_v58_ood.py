"""Frozen OOD benchmark with real Vietoris-Rips H0 and held-out geometry.

H0 persistence is computed by Kruskal on the complete Euclidean graph: its
finite deaths equal MST edge lengths. This does NOT compute persistent H1 or
claim dDCA/SAE equivalence. Score calibration is permitted only on development
in-distribution samples, never on held-out truth. Not an access-control gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from statistics import NormalDist

import numpy as np
from scipy.spatial import cKDTree

from .ontos_testbed import replay
from .ontos_v54_phase0 import PHASE0_SEEDS, TAPES


def _clean_points(points: object, *, bound: int) -> tuple[tuple[float, ...], ...]:
    if type(points) is not tuple or not 1 <= len(points) <= bound:
        raise ValueError('point count outside bounded model')
    dimension = None
    result = []
    for row in points:
        if (type(row) is not tuple or not 2 <= len(row) <= 16
                or (dimension is not None and len(row) != dimension)
                or any(type(v) not in (float, int) or not math.isfinite(v)
                       or abs(v) > 1e6 for v in row)):
            raise ValueError('nonfinite, ragged or unsafe feature vector')
        dimension = len(row)
        result.append(tuple(float(x) for x in row))
    return tuple(result)


def vr_h0_deaths(points: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    """All finite H0 death radii in a Euclidean Vietoris-Rips filtration."""
    p = _clean_points(points, bound=64)
    n = len(p)
    if n == 1:
        return ()
    edges = []
    for i in range(n):
        for j in range(i+1,n):
            length = math.dist(p[i],p[j])
            edges.append((length,i,j))
    edges.sort()
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    deaths = []
    for distance,i,j in edges:
        ai,aj = find(i),find(j)
        if ai == aj:
            continue
        parent[aj] = ai
        deaths.append(distance)
        if len(deaths) == n-1:
            break
    return tuple(deaths)


@dataclass(frozen=True,slots=True)
class CalibratedOOD:
    reference: tuple[tuple[float, ...], ...]
    threshold: float
    fpr_target: float
    dev_id_count: int
    dev_empirical_fpr: float

    def __post_init__(self):
        _clean_points(self.reference,bound=5000)
        if (type(self.threshold) is not float or not math.isfinite(self.threshold)
                or self.threshold < 0 or type(self.fpr_target) is not float
                or not 0 < self.fpr_target <= .5
                or type(self.dev_id_count) is not int or not 1 <= self.dev_id_count <= 5000
                or type(self.dev_empirical_fpr) is not float
                or not 0 <= self.dev_empirical_fpr <= self.fpr_target+1e-12):
            raise ValueError('calibration contract')


def _distances(reference: tuple[tuple[float, ...], ...],
               queries: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    tree=cKDTree(np.asarray(reference,dtype=np.float64))
    distances=tree.query(np.asarray(queries,dtype=np.float64),k=1,workers=1)[0]
    return tuple(float(x) for x in np.atleast_1d(distances))


def fit_ood(reference: tuple[tuple[float, ...], ...],
            dev_id: tuple[tuple[float, ...], ...],
            *, fpr_target: float=.05) -> CalibratedOOD:
    """Use *only* ID data from dev: no held-out labels or OOD examples."""
    ref=_clean_points(reference,bound=5000)
    dev=_clean_points(dev_id,bound=5000)
    if len(ref[0]) != len(dev[0]) or type(fpr_target) is not float or not 0 < fpr_target <= .5:
        raise ValueError('calibration parameters')
    scores=sorted(_distances(ref,dev))
    index=max(0,min(len(scores)-1, math.ceil((1-fpr_target)*len(scores))-1))
    threshold=float(scores[index])
    fpr=sum(x>threshold for x in scores)/len(scores)
    return CalibratedOOD(ref,threshold,float(fpr_target),len(dev),float(fpr))


def score_ood(model: CalibratedOOD,
              points: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    if type(model) is not CalibratedOOD:
        raise ValueError('calibrated detector required')
    model.__post_init__()
    query=_clean_points(points,bound=5000)
    if len(query[0]) != len(model.reference[0]):
        raise ValueError('feature-space dimension mismatch')
    return _distances(model.reference,query)


def _auc(scores: tuple[float, ...], truth: tuple[bool,...]) -> float | None:
    # Exact midrank pairwise probability with tied scores, O(n log n).
    npos=sum(truth); nneg=len(truth)-npos
    if not npos or not nneg:
        return None
    samples=sorted(zip(scores,truth),key=lambda row:row[0])
    negatives_before=0
    correct=0.
    i=0
    while i < len(samples):
        j=i+1
        while j < len(samples) and samples[j][0] == samples[i][0]:
            j+=1
        positives=sum(flag for _,flag in samples[i:j])
        negatives=j-i-positives
        correct+=positives*(negatives_before+negatives/2.)
        negatives_before+=negatives
        i=j
    return correct/(npos*nneg)


def _average_precision(scores: tuple[float, ...],truth: tuple[bool,...]) -> float | None:
    positives=sum(truth)
    if positives == 0:
        return None
    samples=sorted(zip(scores,truth),key=lambda row:-row[0])
    true_seen=0
    total_seen=0
    area=0.
    i=0
    while i < len(samples):
        j=i+1
        while j<len(samples) and samples[j][0]==samples[i][0]:
            j+=1
        newly=sum(flag for _,flag in samples[i:j])
        true_seen+=newly
        total_seen+=j-i
        area+=(newly/positives)*(true_seen/total_seen)
        i=j
    return area


def _wilson(success: int,total: int) -> tuple[float,float] | None:
    if total == 0:
        return None
    z=1.959963984540054
    p=success/total
    z2=z*z
    denom=1+z2/total
    center=(p+z2/(2*total))/denom
    rad=z/denom*math.sqrt(p*(1-p)/total+z2/(4*total**2))
    return (max(0.,center-rad),min(1.,center+rad))


def evaluate_ood(model: CalibratedOOD,
                 features: tuple[tuple[float, ...], ...],
                 truth: tuple[bool, ...]) -> dict:
    """Scorer-only evaluation: feature-only detector does not receive truth."""
    if (type(truth) is not tuple or len(truth)!=len(features)
            or any(type(x) is not bool for x in truth)):
        raise ValueError('heldout ground-truth contract')
    scores=score_ood(model,features)
    tp=fp=tn=fn=pa=na=0
    for score,label in zip(scores,truth):
        predicted = None if score == model.threshold else score > model.threshold
        if predicted is None:
            if label: pa+=1
            else: na+=1
        elif predicted:
            if label: tp+=1
            else: fp+=1
        else:
            if label: fn+=1
            else: tn+=1
    positive=tp+fn+pa
    negative=tn+fp+na
    evaluated_positive=tp+fn
    evaluated_negative=fp+tn
    return {
        'status':'EVALUATED_HOLDOUT','release_approved':False,
        'total':len(truth),'positive':positive,'negative':negative,
        'tp':tp,'fp':fp,'tn':tn,'fn':fn,
        'confusion':{'tp':tp,'fp':fp,'tn':tn,'fn':fn,
                     'positive_abstain':pa,'negative_abstain':na},
        'abstentions':pa+na,'coverage':1-(pa+na)/len(truth),
        'recall':tp/evaluated_positive if evaluated_positive else None,
        'false_positive_rate':fp/evaluated_negative if evaluated_negative else None,
        'unconditional_recall':tp/positive if positive else None,
        'unconditional_false_positive_rate':fp/negative if negative else None,
        'recall_wilson_95':_wilson(tp,positive),
        'fpr_wilson_95':_wilson(fp,negative),
        'roc_auc':_auc(scores,truth),'average_precision':_average_precision(scores,truth),
        'threshold':model.threshold,'threshold_calibrated_on_dev_only':True,
        'score_type':'minimum Euclidean distance; not persistent H1/dDCA',
    }


def run_suite_c() -> dict:
    """Pinned 10 reference / 10 calibration / 10 holdout seeds from v54."""
    seeds=PHASE0_SEEDS
    ref_seeds=seeds[:10]
    cal_seeds=seeds[10:20]
    hold_seeds=seeds[20:]
    tape=TAPES['A_cycle']

    def extract(cohort: tuple[int,...]):
        vectors=[]
        labels=[]
        for seed in cohort:
            for scored in replay(seed,tape):
                vectors.append(scored.observation.continuous)
                labels.append(scored.ood)
        return tuple(vectors),tuple(labels)

    ref,ref_truth=extract(ref_seeds)
    dev,dev_truth=extract(cal_seeds)
    held,held_truth=extract(hold_seeds)
    reference_id=tuple(vector for vector,label in zip(ref,ref_truth) if not label)
    calibration_id=tuple(vector for vector,label in zip(dev,dev_truth) if not label)
    detector=fit_ood(reference_id,calibration_id,fpr_target=.05)
    result=evaluate_ood(detector,held,held_truth)
    # Genuine finite H0 Vietoris-Rips diagnostics on predeclared bounded subsets.
    # These are scorer-only summaries, not an OOD approval signal.
    h0 = {
        'dev_reference': vr_h0_deaths(reference_id[:32]),
        'holdout': vr_h0_deaths(held[:32]),
    }
    h0_summary = {
        key: {'finite_deaths':len(deaths), 'max_death':max(deaths),
              'total_persistence':math.fsum(deaths)}
        for key,deaths in h0.items()
    }
    recall=result['unconditional_recall']
    fpr=result['unconditional_false_positive_rate']
    cohort_sha=lambda s:sha256(json.dumps(s,separators=(',',':')).encode('ascii')).hexdigest()
    return {
        'status':result['status'],'release_approved':False,
        'selection_rule':'first 10 dev-reference, next 10 dev-calibration, final 10 holdout; fixed before scoring',
        'dev_reference_seeds':len(ref_seeds),'dev_calibration_seeds':len(cal_seeds),
        'holdout_seeds':len(hold_seeds),'dev_reference_count':len(reference_id),
        'dev_calibration_count':len(calibration_id),
        'holdout_rows':len(held),'holdout_positive':result['positive'],
        'holdout_negative':result['negative'],
        'dev_empirical_fpr':detector.dev_empirical_fpr,
        'threshold':detector.threshold,
        'holdout_recall':recall,'holdout_fpr':fpr,
        'recall_wilson_95':result['recall_wilson_95'],
        'fpr_wilson_95':result['fpr_wilson_95'],
        'coverage':result['coverage'],'roc_auc':result['roc_auc'],
        'average_precision':result['average_precision'],
        'confusion':result['confusion'],
        'meets_70_recall_5_fpr_target':(recall is not None and fpr is not None
                                      and recall >= .70 and fpr <= .05),
        'confidence_gate_95_passed':(result['recall_wilson_95'] is not None
                                     and result['fpr_wilson_95'] is not None
                                     and result['recall_wilson_95'][0] >= .70
                                     and result['fpr_wilson_95'][1] <= .05),
        'dev_reference_sha256':cohort_sha(ref_seeds),
        'holdout_sha256':cohort_sha(hold_seeds),
        'cohort_digest_is_manifest_not_full_features':True,
        'persistent_h0_diagnostics':'Euclidean VR H0 on 32-point bounded cohorts, not H1/dDCA',
        'h0_cohort_subset_size':32,
        'h0_cohort_diagnostics':h0_summary,
    }
