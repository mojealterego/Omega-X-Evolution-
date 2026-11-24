"""Bounded persistent homology and sampling diagnostics for latent representations.

Vietoris-Rips filtration through triangles, homology H0/H1 over GF(2).
All inputs are finite; this is a small-sample mathematical diagnostic, not
JEPA/SIGReg integration, a prevention theorem, or an RSI admission mechanism.
"""
from __future__ import annotations

from itertools import combinations
import argparse
import json
import math
from pathlib import Path
import random
from typing import Any

import numpy as np

MAX_POINTS = 24
MAX_DIMENSIONS = 16
MAX_BATCH_ROWS = 4096
MAX_OBSERVATIONS = 100_000_000
MAX_ABS_VALUE = 1_000_000.0


def _points(value: Any, *, min_rows: int = 2, max_rows: int = MAX_POINTS,
            dimensions: int | None = None) -> np.ndarray:
    # Do not invoke untrusted __array__/__iter__ hooks or allocate huge arrays
    # before validating the caller-supplied outer dimensions.
    if type(value) is np.ndarray:
        raw = value
    elif type(value) in (list, tuple):
        if not min_rows <= len(value) <= max_rows:
            raise ValueError('row count exceeds bound')
        if any(type(row) not in (list, tuple) or not 2 <= len(row) <= MAX_DIMENSIONS
               or any(type(item) not in (int, float) for item in row)
               for row in value):
            raise ValueError('invalid latent row shape')
        try:
            raw = np.asarray(value)
        except (ValueError, TypeError, OverflowError, RecursionError) as exc:
            raise ValueError('invalid latent array') from exc
    else:
        raise ValueError('unsupported latent data container')
    if (raw.ndim != 2 or raw.dtype.kind not in 'iuf'
            or not min_rows <= raw.shape[0] <= max_rows
            or not 2 <= raw.shape[1] <= MAX_DIMENSIONS
            or (dimensions is not None and raw.shape[1] != dimensions)):
        raise ValueError('bounded numeric latent matrix required')
    try:
        values = np.array(raw, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('latent conversion rejected') from exc
    if not np.isfinite(values).all() or np.max(np.abs(values)) > MAX_ABS_VALUE:
        raise ValueError('nonfinite or excessive latent magnitude')
    return values


def vietoris_rips_h01(points: Any) -> dict[str, Any]:
    """Compute exact GF(2) reduction on an approximate float64 distance filtration.

    All vertices, all edges and all triangles are inserted. A full 2-skeleton
    suffices for H0/H1 persistence; no H2 persistence is computed. Float64
    distances are approximate, and zero-lifetime H1 intervals are suppressed.
    """
    x = _points(points)
    n, dims = x.shape
    distances = np.linalg.norm(x[:, None, :] - x[None, :, :], axis=2)
    # Filtration key: (diameter, dimension, simplex indices). This ensures all
    # faces appear before their cofaces even for coincident points / tied edges.
    cells: list[tuple[float, int, tuple[int, ...]]] = [(0.0, 0, (i,)) for i in range(n)]
    for a, b in combinations(range(n), 2):
        cells.append((float(distances[a, b]), 1, (a, b)))
    for a, b, c in combinations(range(n), 3):
        cells.append((float(max(distances[a, b], distances[a, c], distances[b, c])), 2, (a, b, c)))
    cells.sort()
    index = {simplex: i for i, (_, _, simplex) in enumerate(cells)}

    # Sparse binary boundary columns represented by Python big-integer bitsets.
    # Each reduction pivot is identified by its highest nonzero row index.
    pivots: dict[int, int] = {}
    paired: set[int] = set()
    born: list[int] = []
    h0: list[tuple[float, float]] = []
    h1: list[tuple[float, float]] = []
    for col, (death_time, dim, simplex) in enumerate(cells):
        if dim == 0:
            reduced = 0
        else:
            reduced = 0
            for face in combinations(simplex, dim):
                reduced ^= 1 << index[face]
        while reduced:
            low = reduced.bit_length() - 1
            if low not in pivots:
                break
            reduced ^= pivots[low]
        if reduced:
            low = reduced.bit_length() - 1
            pivots[low] = reduced
            paired.add(low)
            birth_time, birth_dim, _ = cells[low]
            if birth_dim == 0:
                h0.append((birth_time, death_time))
            elif birth_dim == 1 and death_time > birth_time:
                h1.append((birth_time, death_time))
        else:
            born.append(col)

    essential_h0 = [cells[i][0] for i in born if i not in paired and cells[i][1] == 0]
    essential_h1 = [cells[i][0] for i in born if i not in paired and cells[i][1] == 1]
    h0.sort()
    h1.sort()
    return {
        'schema': 'ontos-vr-h01-v1', 'coefficient_field': 'GF(2)',
        'n_points': n, 'dimensions': dims, 'n_simplices': len(cells),
        'h0_finite': h0, 'h0_essential': essential_h0,
        'h1_finite': h1, 'h1_essential': essential_h1,
        'release_authorized': False, 'jepa_model_verified': False,
        'long_context_guaranteed': False,
    }


def diagnose_latents(points: Any, *, min_rank: int = 2) -> dict[str, Any]:
    """Diagnostic only: variance-collapse indicator plus H0/H1 intervals.

    Rank is scale-relative and is not proof of neural representation collapse.
    """
    x = _points(points)
    if type(min_rank) is not int or not 1 <= min_rank <= MAX_DIMENSIONS:
        raise ValueError('rank criterion out of bounds')
    if len(x) < 3:
        raise ValueError('diagnostics require at least three points')
    centered = x - np.mean(x, axis=0)
    singular = np.linalg.svd(centered, full_matrices=False, compute_uv=False)
    leading = float(singular[0])
    if leading <= 1e-12:
        rank, effective = 0, 0.0
        status = 'POTENTIAL_COLLAPSE_CONSTANT'
    else:
        squared = singular ** 2
        fractions = squared / math.fsum(float(v) for v in squared)
        positive = fractions[fractions > 0]
        effective = float(math.exp(-float(np.sum(positive * np.log(positive)))))
        rank = int(np.count_nonzero(singular > leading * 1e-8))
        status = 'POTENTIAL_LOW_RANK' if rank < min_rank else 'NO_COLLAPSE_SIGNAL_IN_SAMPLE'
    persistence = vietoris_rips_h01(x)
    return {
        'schema': 'ontos-latent-diagnostic-v1',
        'status': status,
        'sampled': len(x), 'dimensions': x.shape[1],
        'affine_rank': rank, 'effective_rank': effective,
        'max_h1_persistence': max((d-b for b, d in persistence['h1_finite']), default=0.0),
        'h1_finite': persistence['h1_finite'],
        'h0_finite': persistence['h0_finite'],
        'release_authorized': False,
        'jepa_model_verified': False,
        'long_context_guaranteed': False,
    }


class LatentReservoir:
    """Deterministic bounded uniform reservoir of supplied latent vectors.

    Ingest accepts only precomputed vectors. No model weights, prompts, private
    text or token contents are processed or exported. Reservoir sampling gives
    no statistical guarantee of topology preservation on full token streams.
    """
    def __init__(self, *, dimensions: int, capacity: int = MAX_POINTS,
                 seed: int = 42, max_observations: int = MAX_OBSERVATIONS):
        if (type(dimensions) is not int or not 2 <= dimensions <= MAX_DIMENSIONS
                or type(capacity) is not int or not 3 <= capacity <= MAX_POINTS
                or type(seed) is not int or not 0 <= seed < 2**32
                or type(max_observations) is not int
                or not 3 <= max_observations <= MAX_OBSERVATIONS):
            raise ValueError('invalid reservoir policy')
        self.dimensions = dimensions
        self.capacity = capacity
        self.max_observations = max_observations
        self._rng = random.Random(seed)
        self._sample: list[np.ndarray] = []
        self.observed = 0

    @property
    def sampled(self) -> int:
        return len(self._sample)

    def ingest(self, vectors: Any) -> int:
        batch = _points(vectors, min_rows=1, max_rows=MAX_BATCH_ROWS,
                        dimensions=self.dimensions)
        if self.observed + len(batch) > self.max_observations:
            raise ValueError('observation budget exceeded')
        for row in batch:
            self.observed += 1
            if len(self._sample) < self.capacity:
                self._sample.append(row.copy())
            else:
                i = self._rng.randrange(self.observed)
                if i < self.capacity:
                    self._sample[i] = row.copy()
        return self.observed

    def sample(self) -> np.ndarray:
        """Explicit local-only copy; callers are responsible for data privacy."""
        if not self._sample:
            return np.empty((0, self.dimensions), dtype=np.float64)
        return np.stack(self._sample, axis=0)

    def diagnose(self, *, min_rank: int = 2) -> dict[str, Any]:
        if type(min_rank) is not int or not 1 <= min_rank <= MAX_DIMENSIONS:
            raise ValueError('rank criterion out of bounds')
        if self.sampled < 3:
            return {
                'schema': 'ontos-latent-diagnostic-v1',
                'status': 'UNKNOWN_INSUFFICIENT_SAMPLE',
                'observed': self.observed, 'sampled': self.sampled,
                'sampling_mode': 'reservoir_uniform_without_replacement',
                'release_authorized': False, 'jepa_model_verified': False,
                'long_context_guaranteed': False,
            }
        report = diagnose_latents(self.sample(), min_rank=min_rank)
        # Do not leak raw embeddings in the serialized diagnostic.
        return {**report, 'observed': self.observed,
                'sampling_mode': 'reservoir_uniform_without_replacement'}


def _read_json(raw: str) -> Any:
    def no_special(_: str) -> None:
        raise ValueError('nonstandard JSON numeric value')
    def distinct(pairs):
        d = {}
        for k, v in pairs:
            if k in d:
                raise ValueError('duplicate JSON key')
            d[k] = v
        return d
    return json.loads(raw, parse_constant=no_special, object_pairs_hook=distinct)


def main() -> None:
    """Data-only CLI. JSON for small clouds; JSONL for bounded-memory sampling."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--format', choices=('json', 'jsonl'), default='json')
    parser.add_argument('--dimensions', type=int)
    parser.add_argument('--capacity', type=int, default=MAX_POINTS)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--min-rank', type=int, default=2)
    parser.add_argument('--max-observations', type=int, default=MAX_OBSERVATIONS)
    args = parser.parse_args()
    try:
        if args.format == 'json':
            with args.input.open('rb') as handle:
                raw = handle.read(131073)
            if len(raw) > 131072:
                raise ValueError('JSON input exceeds 128 KiB')
            report = diagnose_latents(_read_json(raw.decode('utf-8')), min_rank=args.min_rank)
        else:
            if args.dimensions is None:
                raise ValueError('JSONL requires --dimensions')
            reservoir = LatentReservoir(dimensions=args.dimensions, capacity=args.capacity,
                                        seed=args.seed, max_observations=args.max_observations)
            with args.input.open('r', encoding='utf-8') as handle:
                for number, line in enumerate(handle, 1):
                    if len(line.encode('utf-8')) > 4096:
                        raise ValueError(f'line too long at {number}')
                    row = _read_json(line)
                    reservoir.ingest([row])
            report = reservoir.diagnose(min_rank=args.min_rank)
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
        return
    print(json.dumps(report, allow_nan=False, sort_keys=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
