"""Native elapsed/CPU time observations for the fixed living-memory paths.

Timing is intentionally nondeterministic. No calibrated energy, hardware FLOP,
allocator peak or production latency claims. Process CPU includes other threads;
thread CPU excludes work delegated to BLAS workers. No caller callback API.
"""
from __future__ import annotations

from statistics import median_low
from time import perf_counter_ns, process_time_ns, thread_time_ns

from .ontos_living_memory import Batch, diagnose, review_candidate
from .ontos_authenticated_boundary import BoundaryPlan, SignedEnvelope
from .ontos_v51_sequential_memory import ReviewPlan, SignedTrial


def _profile(batch, repeats, scope, operation):
    if type(batch) is not Batch or type(repeats) is not int or not 1<=repeats<=32:
        raise ValueError('bounded profiling input')
    candidate=batch.sha256
    samples=[]; first=None
    for _ in range(repeats):
        wall=perf_counter_ns(); cpu=process_time_ns(); thread=thread_time_ns()
        result=operation()
        elapsed_thread=thread_time_ns()-thread
        elapsed_cpu=process_time_ns()-cpu
        elapsed_wall=perf_counter_ns()-wall
        if min(elapsed_thread,elapsed_cpu,elapsed_wall)<0:
            raise RuntimeError('native clock regressed')
        if first is None: first=result
        elif result!=first: raise RuntimeError('diagnostic replay diverged')
        samples.append({'wall_ns':elapsed_wall,'process_cpu_ns':elapsed_cpu,'thread_cpu_ns':elapsed_thread})
    return {'scope':scope,'candidate_sha256':candidate,'samples':tuple(samples),
            'median_low':{k:median_low(s[k] for s in samples) for k in samples[0]},
            'result':first,'energy_joules':None,'hardware_flops':None,'peak_memory_bytes':None,
            'process_isolation_verified':False,'promotion_authorized':False}


def profile_diagnostic(batch: Batch, *, repeats: int=5) -> dict:
    """Measure complete offline train + recall + prediction, including validation."""
    return _profile(batch,repeats,'OFFLINE_DIAGNOSTIC',lambda:diagnose(batch))


def profile_review(batch: Batch, plan: ReviewPlan, plan_pin: str,
                   trials: tuple[SignedTrial,...], evidence_head: str,
                   boundary: BoundaryPlan, boundary_pin: str,
                   messages: tuple[SignedEnvelope,...], boundary_head: str,
                   *, repeats: int=5) -> dict:
    """Measure full gated replay, not just the successful memory kernel."""
    return _profile(batch,repeats,'AUTHENTICATED_REVIEW',lambda:review_candidate(
        batch,plan,plan_pin,trials,evidence_head,boundary,boundary_pin,messages,boundary_head))
