"""ONTOS L11 v71 — conservative, bounded multiobjective energy comparison.

Runs the real v69 scenario model. Every numeric input is an *operator scenario*;
no physical calibration, statistical interval, or hardware Pareto superiority
is inferred. Ambiguous or missing interval inputs remain UNKNOWN.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re

from .ontos_v69_substrate import SubstrateScenario

_MAX_COUNT = 10**15
_MAX_ENERGY_J = 10**15
_MAX_CANDIDATES = 64
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z", re.ASCII)


def _finite_range(value: object, low: float, high: float) -> bool:
    # Compare before math.isfinite: Python 10**400 must fail as ValueError,
    # not an unexpected int-to-float OverflowError.
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class Interval:
    """Operator-supplied correctness interval in [0,1], NOT a confidence interval."""

    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not (_finite_range(self.lower, 0., 1.) and
                _finite_range(self.upper, 0., 1.) and self.lower <= self.upper):
            raise ValueError("invalid correctness interval")


@dataclass(frozen=True, slots=True)
class Workload:
    """Exact comparable workload identity and a required correctness threshold."""

    fingerprint_sha256: str
    operations: int
    min_correctness: float
    target_wall_j: float | None = None

    def __post_init__(self) -> None:
        if type(self.fingerprint_sha256) is not str or not _SHA.fullmatch(self.fingerprint_sha256):
            raise ValueError("invalid workload fingerprint")
        if type(self.operations) is not int or not 1 <= self.operations <= _MAX_COUNT:
            raise ValueError("invalid operation count")
        if not _finite_range(self.min_correctness, 0., 1.):
            raise ValueError("invalid correctness threshold")
        if self.target_wall_j is not None and not _finite_range(self.target_wall_j, 0., _MAX_ENERGY_J):
            raise ValueError("invalid wall energy target")


@dataclass(frozen=True, slots=True)
class Candidate:
    """Single v69 scenario for the specified workload with bounded time sensitivity."""

    identifier: str
    workload_sha256: str
    operations: int
    scenario: SubstrateScenario
    correctness: Interval
    runtime_uncertainty_rel: float = 0.

    def __post_init__(self) -> None:
        if type(self.identifier) is not str or not _ID.fullmatch(self.identifier):
            raise ValueError("invalid candidate identifier")
        if type(self.workload_sha256) is not str or not _SHA.fullmatch(self.workload_sha256):
            raise ValueError("invalid candidate workload fingerprint")
        if type(self.operations) is not int or not 1 <= self.operations <= _MAX_COUNT:
            raise ValueError("invalid candidate operation count")
        if type(self.scenario) is not SubstrateScenario or type(self.correctness) is not Interval:
            raise ValueError("validated scenario and correctness required")
        self.scenario.__post_init__()
        self.correctness.__post_init__()
        if not 0 < self.scenario.duration_s <= 1e9:
            raise ValueError("duration must be positive for performance comparison")
        if not _finite_range(self.runtime_uncertainty_rel, 0., 1.):
            raise ValueError("invalid relative time sensitivity")


def _bounded_threeway(value: Interval, threshold: float) -> str:
    if value.lower >= threshold:
        return "PASS_SCENARIO"
    if value.upper < threshold:
        return "FAIL_SCENARIO"
    return "UNKNOWN"


def _target_status(bounds: dict | None, threshold: float | None) -> str:
    if bounds is None or threshold is None:
        return "UNKNOWN"
    if bounds["upper"] <= threshold:
        return "PASS_SCENARIO"
    if bounds["lower"] > threshold:
        return "FAIL_SCENARIO"
    return "UNKNOWN"


def _energy_bounds(candidate: Candidate) -> dict | None:
    report = candidate.scenario.report()
    central = report["energy_wall_j"]
    endpoints = report["uncertainty_interval_wall_j"]
    if central is None or endpoints is None:
        return None
    low, high = endpoints
    if not (_finite_range(low, 0., _MAX_ENERGY_J) and
            _finite_range(high, 0., _MAX_ENERGY_J) and low <= central <= high):
        raise ValueError("wall-energy scenario overflow")
    return {"lower": low, "central": central, "upper": high}


def _metrics(candidate: Candidate) -> tuple[dict | None, dict, dict]:
    energy = _energy_bounds(candidate)
    seconds = candidate.scenario.duration_s
    uncertainty = candidate.runtime_uncertainty_rel
    duration = {"lower": seconds * (1. - uncertainty),
                "central": seconds,
                "upper": seconds * (1. + uncertainty)}
    quality = {"lower": candidate.correctness.lower, "upper": candidate.correctness.upper}
    if not all(math.isfinite(x) for x in duration.values()):
        raise ValueError("duration sensitivity overflow")
    return energy, duration, quality


def _dominates_metrics(a: tuple, b: tuple) -> bool:
    energy_a, duration_a, quality_a = a
    energy_b, duration_b, quality_b = b
    if energy_a is None or energy_b is None:
        return False
    comparisons = (
        (energy_a["upper"], energy_b["lower"]),
        (duration_a["upper"], duration_b["lower"]),
        (quality_b["upper"], quality_a["lower"]),
    )
    return all(x <= y for x, y in comparisons) and any(x < y for x, y in comparisons)


def robustly_dominates(a: Candidate, b: Candidate) -> bool:
    """Strict conservative interval dominance for equal declared workloads.

    For minimization of energy and latency and maximization of correctness,
    a *worst* value must beat b's *best* value in every dimension.
    This only establishes dominance within the supplied scenario assumptions.
    """
    if type(a) is not Candidate or type(b) is not Candidate:
        raise ValueError("typed candidates required")
    a.__post_init__(); b.__post_init__()
    if a.workload_sha256 != b.workload_sha256 or a.operations != b.operations:
        raise ValueError("incomparable workloads")
    return _dominates_metrics(_metrics(a), _metrics(b))


def compare(workload: Workload, candidates: tuple[Candidate, ...]) -> dict:
    """Deterministic conservative Pareto frontier, never a release authorization.

    Missing energy, missing sensitivity or threshold-straddling correctness
    leads to UNKNOWN; candidates are not silently removed and no winner is
    claimed if any candidate is unresolved or rejected.
    """
    if type(workload) is not Workload or type(candidates) is not tuple or not 1 <= len(candidates) <= _MAX_CANDIDATES:
        raise ValueError("typed workload and 1..64 candidates required")
    workload.__post_init__()
    if any(type(c) is not Candidate for c in candidates):
        raise ValueError("typed candidates required")
    ordered = sorted(candidates, key=lambda c: c.identifier)
    if len(set(c.identifier for c in ordered)) != len(ordered):
        raise ValueError("duplicate candidate identifiers")
    rows = []
    metrics = {}
    unresolved = []
    rejected = []
    eligible = []
    for c in ordered:
        c.__post_init__()
        if c.workload_sha256 != workload.fingerprint_sha256:
            raise ValueError("workload fingerprint mismatch")
        if c.operations != workload.operations:
            raise ValueError("operations do not match reference workload")
        e, t, q = _metrics(c)
        quality_gate = _bounded_threeway(c.correctness, workload.min_correctness)
        if quality_gate == "FAIL_SCENARIO":
            decision = "FAIL_SCENARIO"
            rejected.append(c.identifier)
        elif quality_gate == "UNKNOWN" or e is None:
            decision = "UNKNOWN"
            unresolved.append(c.identifier)
        else:
            decision = "PASS_SCENARIO"
            eligible.append(c.identifier)
            metrics[c.identifier] = (e,t,q)
        rows.append({
            "id": c.identifier,
            "substrate": c.scenario.substrate,
            "operations": c.operations,
            "energy_j": e,
            "duration_s": t,
            "correctness": q,
            "correctness_threshold": quality_gate,
            "energy_target": _target_status(e, workload.target_wall_j),
            "eligibility": decision,
        })
    dominated = set()
    overlaps = []
    for i, name in enumerate(eligible):
        for other in eligible[i+1:]:
            a, b = metrics[name], metrics[other]
            if a[0]["lower"] <= b[0]["upper"] and b[0]["lower"] <= a[0]["upper"]:
                overlaps.append([name,other])
            if _dominates_metrics(a,b):
                dominated.add(other)
            if _dominates_metrics(b,a):
                dominated.add(name)
    frontier = [name for name in eligible if name not in dominated]
    return {
        "schema": "omega-ontos-v71-scenario-pareto-v1",
        "workload_sha256": workload.fingerprint_sha256,
        "operations": workload.operations,
        "min_correctness": workload.min_correctness,
        "target_wall_j": workload.target_wall_j,
        "candidates": rows,
        "robust_frontier": frontier,
        "robust_dominated": sorted(dominated),
        "energy_overlap_pairs": overlaps,
        "unresolved": unresolved,
        "rejected": rejected,
        "unique_robust_scenario_leader": (len(candidates) > 1 and len(frontier) == 1 and
                                  not unresolved and not rejected and
                                  len(dominated) == len(candidates) - 1),
        "source": "OPERATOR_ASSUMED_SCENARIO",
        "interval_kind": "OPERATOR_SENSITIVITY_NOT_STATISTICAL_CI",
        "physical_measurement_verified": False,
        "release_authorized": False,
    }
