"""Finite Vietoris-Rips persistence H0/H1 and bounded latent reservoir.

Reference checking: independent MST + elementary graph-homology GF(2).
"""
from __future__ import annotations

from itertools import combinations
import json
import math
import random

import numpy as np
import pytest

from omega_x_evolution.ontos_tda import (LatentReservoir, diagnose_latents,
                                         vietoris_rips_h01)


def square(scale: float = 1.0) -> np.ndarray:
    return np.array(((0, 0), (scale, 0), (scale, scale), (0, scale)), dtype=float)


def line(n: int = 5) -> np.ndarray:
    return np.stack((np.arange(n, dtype=float), np.zeros(n)), axis=-1)


def _components(edges, n):
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i, j in edges:
        ri, rj = find(i), find(j)
        parent[ri] = rj
    return len({find(i) for i in range(n)})


def _reference_h1(points: np.ndarray, radius: float) -> int:
    """Independent graph cycle space / rank of triangle boundaries over GF(2)."""
    d = np.linalg.norm(points[:, None, :] - points[None, :, :], axis=2)
    n = len(points)
    edges = [(i, j) for i, j in combinations(range(n), 2) if d[i, j] <= radius]
    position = {e: k for k, e in enumerate(edges)}
    pivots = {}
    for i, j, k in combinations(range(n), 3):
        if (i, j) not in position or (i, k) not in position or (j, k) not in position:
            continue
        bits = (1 << position[i, j]) ^ (1 << position[i, k]) ^ (1 << position[j, k])
        while bits:
            p = bits.bit_length() - 1
            if p in pivots:
                bits ^= pivots[p]
            else:
                pivots[p] = bits
                break
    return len(edges) - n + _components(edges, n) - len(pivots)


def _barcode_betti(report: dict, radius: float) -> int:
    return sum(b <= radius < d for b, d in report['h1_finite']) + len(report['h1_essential'])


def test_square_persistent_hole_and_h0():
    r = vietoris_rips_h01(square())
    assert r['schema'] == 'ontos-vr-h01-v1'
    assert r['n_points'] == 4 and r['dimensions'] == 2
    assert r['coefficient_field'] == 'GF(2)'
    assert len(r['h0_finite']) == 3
    assert all(b == 0.0 and d == pytest.approx(1.0) for b, d in r['h0_finite'])
    assert len(r['h0_essential']) == 1
    assert len(r['h1_finite']) == 1
    assert r['h1_finite'][0] == pytest.approx((1.0, math.sqrt(2)))
    assert r['h1_essential'] == []
    assert r['release_authorized'] is False


def test_two_clusters_have_late_merge():
    points = np.array(((0, 0), (0, 1), (10, 0), (10, 1)), dtype=float)
    r = vietoris_rips_h01(points)
    assert sorted(d for _, d in r['h0_finite']) == pytest.approx((1, 1, 10))


def test_collinear_triangle_and_duplicate_examples():
    assert vietoris_rips_h01(line())['h1_finite'] == []
    assert vietoris_rips_h01(np.array(((0, 0), (1, 0), (0.5, 0.7))))['h1_finite'] == []
    dupe = np.zeros((5, 2), dtype=float)
    r = vietoris_rips_h01(dupe)
    assert len(r['h0_finite']) == 4
    assert all(pair == (0, 0) for pair in r['h0_finite'])
    assert not r['h1_finite']


def test_permutation_translation_and_scale_invariance():
    points = square()
    original = vietoris_rips_h01(points)
    for ids in ((2, 0, 3, 1), (1, 3, 2, 0)):
        moved = points[list(ids)] + (100, -90)
        assert vietoris_rips_h01(moved)['h1_finite'] == pytest.approx(original['h1_finite'])
    large = vietoris_rips_h01(points * 3)
    assert np.asarray(large['h1_finite']) == pytest.approx(np.asarray(original['h1_finite']) * 3)


@pytest.mark.parametrize('seed', range(15))
def test_random_topology_matches_independent_betti_and_h0(seed):
    pts = np.random.default_rng(seed).normal(size=(5 + seed % 5, 2))
    r = vietoris_rips_h01(pts)
    distances = sorted(float(np.linalg.norm(pts[i] - pts[j])) for i, j in combinations(range(len(pts)), 2))
    for radius in ((distances[0] + distances[1]) / 2,
                   (distances[len(distances)//3] + distances[len(distances)//3+1]) / 2,
                   (distances[-2] + distances[-1]) / 2, distances[-1] + 1):
        assert _barcode_betti(r, radius) == _reference_h1(pts, radius)
    # Independent MST from Kruskal's algorithm.
    parent = list(range(len(pts)))
    def root(i):
        while parent[i] != i:
            i = parent[i]
        return i
    mst = []
    for d, i, j in sorted((float(np.linalg.norm(pts[i]-pts[j])), i, j) for i, j in combinations(range(len(pts)), 2)):
        a, b = root(i), root(j)
        if a != b:
            parent[a] = b
            mst.append(d)
    assert sorted(d for _, d in r['h0_finite']) == pytest.approx(sorted(mst))


def test_diagnosis_reports_constant_or_low_rank_but_never_authorizes():
    constant = diagnose_latents(np.zeros((5, 4)))
    assert constant['status'] == 'POTENTIAL_COLLAPSE_CONSTANT'
    assert constant['effective_rank'] == 0.0
    linear = diagnose_latents(np.array([[i, 2*i, 3*i] for i in range(6)]))
    assert linear['status'] == 'POTENTIAL_LOW_RANK'
    ring = diagnose_latents(square())
    assert ring['status'] == 'NO_COLLAPSE_SIGNAL_IN_SAMPLE'
    assert ring['max_h1_persistence'] == pytest.approx(math.sqrt(2) - 1)
    for report in (constant, linear, ring):
        assert report['release_authorized'] is False
        assert report['jepa_model_verified'] is False
        assert report['long_context_guaranteed'] is False


def test_rank_threshold_input_and_stable_shape():
    pts = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
    assert diagnose_latents(pts, min_rank=3)['status'] == 'POTENTIAL_LOW_RANK'
    assert diagnose_latents(pts, min_rank=2)['status'] == 'NO_COLLAPSE_SIGNAL_IN_SAMPLE'
    with pytest.raises(ValueError): diagnose_latents(pts, min_rank=0)
    with pytest.raises(ValueError): diagnose_latents(pts, min_rank=True)


@pytest.mark.parametrize('bad', [
    [], [[0]], [[0, 0]], np.zeros((25, 2)), np.zeros((3, 17)),
    [[0, 0], [1, float('nan')]], [[0, 0], [1, float('inf')]],
    [[0, 0], [1, 1e7]], [[True, False], [False, True]],
    [[0, 0], ['x', 'y']], np.zeros((3, 2, 1)), np.array([[0, 1],[1, 0]], dtype=object)
])
def test_validation_rejects_invalid_or_unbounded_data(bad):
    with pytest.raises(ValueError): vietoris_rips_h01(bad)


def test_exact_limit_24_and_no_unbounded_memory():
    pts = np.random.default_rng(99).normal(size=(24, 3))
    r = vietoris_rips_h01(pts)
    assert r['n_points'] == 24
    assert r['n_simplices'] == 24 + 276 + 2024
    assert len(r['h0_finite']) == 23


def test_streaming_reservoir_is_bounded_and_chunking_deterministic():
    rows = np.random.default_rng(4).normal(size=(129, 3))
    a, b = LatentReservoir(dimensions=3, capacity=12, seed=9), LatentReservoir(dimensions=3, capacity=12, seed=9)
    for chunk in np.array_split(rows, 7): a.ingest(chunk)
    for chunk in np.array_split(rows, 17): b.ingest(chunk)
    assert a.observed == b.observed == len(rows)
    assert a.sampled == b.sampled == 12
    assert np.array_equal(a.sample(), b.sample())
    assert a.diagnose() == b.diagnose()


def test_stream_budget_validation_atomicity_and_no_raw_export():
    r = LatentReservoir(dimensions=2, capacity=3, seed=10, max_observations=5)
    r.ingest([[0, 0], [1, 1]])
    assert r.observed == 2
    with pytest.raises(ValueError): r.ingest([[1, 2], [2, 3], [3, 4], [4, 5]])
    assert r.observed == 2
    with pytest.raises(ValueError): r.ingest([[0, 0, 0]])
    assert r.observed == 2
    with pytest.raises(ValueError): r.ingest([[float('nan'), 1]])
    assert r.observed == 2
    assert 'points' not in json.dumps(r.diagnose())
    with pytest.raises(ValueError): LatentReservoir(dimensions=True)
    with pytest.raises(ValueError): LatentReservoir(dimensions=2, capacity=25)


def test_two_observations_report_unknown_instead_of_promotion():
    r = LatentReservoir(dimensions=2, capacity=4, seed=1)
    assert r.diagnose()['status'] == 'UNKNOWN_INSUFFICIENT_SAMPLE'
    r.ingest([[1, 2]])
    assert r.diagnose()['status'] == 'UNKNOWN_INSUFFICIENT_SAMPLE'


def test_stream_reports_only_bounded_sample_not_millions_claim():
    r = LatentReservoir(dimensions=2, capacity=4, seed=5)
    for _ in range(40): r.ingest([[1, 0], [0, 1], [2, 2], [2, 0]])
    d = r.diagnose()
    assert d['observed'] == 160 and d['sampled'] == 4
    assert d['sampling_mode'] == 'reservoir_uniform_without_replacement'
    assert d['long_context_guaranteed'] is False


def test_untrusted_array_protocol_never_called():
    class Malicious:
        def __array__(self, dtype=None):
            raise AssertionError('untrusted conversion hook invoked')
    with pytest.raises(ValueError): vietoris_rips_h01(Malicious())


def test_cli_json_and_jsonl_are_bounded_and_data_only(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    direct = tmp_path / 'square.json'
    direct.write_text(json.dumps(square().tolist()), encoding='utf-8')
    command = [sys.executable, '-m', 'omega_x_evolution.ontos_tda', '--input', str(direct)]
    ran = subprocess.run(command, text=True, capture_output=True, env=env, timeout=8)
    assert ran.returncode == 0, ran.stderr
    result = json.loads(ran.stdout)
    assert result['status'] == 'NO_COLLAPSE_SIGNAL_IN_SAMPLE'
    assert 'points' not in ran.stdout
    assert result['max_h1_persistence'] == pytest.approx(math.sqrt(2) - 1)

    stream = tmp_path / 'stream.jsonl'
    stream.write_text('\n'.join(json.dumps(row) for row in line(8).tolist())+'\n', encoding='utf-8')
    command = [sys.executable, '-m', 'omega_x_evolution.ontos_tda', '--input', str(stream),
               '--format', 'jsonl', '--dimensions', '2', '--capacity', '4', '--seed', '4']
    ran = subprocess.run(command, text=True, capture_output=True, env=env, timeout=8)
    assert ran.returncode == 0, ran.stderr
    result = json.loads(ran.stdout)
    assert result['observed'] == 8 and result['sampled'] == 4
    assert result['status'] == 'POTENTIAL_LOW_RANK'
    assert result['release_authorized'] is False

    stream.write_text('[1,2]\n[false, 9]\n', encoding='utf-8')
    ran = subprocess.run(command, text=True, capture_output=True, env=env, timeout=8)
    assert ran.returncode != 0
    assert not ran.stdout
    assert 'Traceback' not in ran.stderr


def test_cli_strict_json_and_line_bounds(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1])
    source = tmp_path / 'data.jsonl'
    command = [sys.executable, '-m', 'omega_x_evolution.ontos_tda', '--input', str(source),
               '--format', 'jsonl', '--dimensions', '2']
    for data in ('[1,NaN]\n', '[1,2]\n'+' '*4098+'[1,2]\n',
                 '[1,2]\n[1,2]\n[1,2]\n' + '[2,4]\n'*100):
        source.write_text(data, encoding='utf-8')
        args = command + ['--max-observations', '5']
        ran = subprocess.run(args, text=True, capture_output=True, env=env, timeout=8)
        assert ran.returncode != 0 and 'Traceback' not in ran.stderr


def test_main_direct_coverage_json_jsonl_and_validation(monkeypatch, capsys, tmp_path):
    import sys
    from omega_x_evolution.ontos_tda import main
    p = tmp_path / 'a.json'
    p.write_text(json.dumps(square().tolist()), encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(p)])
    main()
    obj = json.loads(capsys.readouterr().out)
    assert obj['h1_finite'] == [[1.0, pytest.approx(math.sqrt(2))]]

    p.write_text('[0,1]\n[1,1]\n[1,0]\n', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(p), '--format', 'jsonl',
                                      '--capacity', '3', '--dimensions', '2', '--seed', '0'])
    main()
    obj = json.loads(capsys.readouterr().out)
    assert obj['sampled'] == 3 and obj['observed'] == 3
    assert obj['release_authorized'] is False
    p.write_text('[[1,1],[1,1],[1,1]]', encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(p)])
    main()
    assert json.loads(capsys.readouterr().out)['status'] == 'POTENTIAL_COLLAPSE_CONSTANT'


@pytest.mark.parametrize('data, args', [
    ('{"a":1,"a":2}', []),
    ('[[0,0],[1,1],[1,NaN]]', []),
    ('['+'0'*131073+']', []),
    ('[1,2]\n', ['--format','jsonl']),
    ('[1,2]\n', ['--format','jsonl','--dimensions','17']),
    ('[1,2]\n[1,2]\n[1,2]\n[1,2]\n', ['--format','jsonl','--dimensions','2','--max-observations','3']),
    ('[1,2]\n'+' '*4100+'[2,3]\n', ['--format','jsonl','--dimensions','2']),
])
def test_main_direct_rejects_invalid_input(monkeypatch, tmp_path, data, args):
    import sys
    from omega_x_evolution.ontos_tda import main
    p = tmp_path / 'a.json'
    p.write_text(data, encoding='utf-8')
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(p), *args])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2


def test_rank_and_reservoir_defensive_api():
    r = LatentReservoir(dimensions=2, capacity=3)
    assert r.sample().shape == (0, 2)
    with pytest.raises(ValueError): r.diagnose(min_rank=100)
    r.ingest([[0,0],[1,0],[0,1],[2,2]])
    p = r.sample()
    p[:] = 123
    assert not np.all(r.sample() == 123)
    with pytest.raises(ValueError): diagnose_latents(np.array([[0., 0.], [1., 1.]]))
    with pytest.raises(ValueError): LatentReservoir(dimensions=2, max_observations=2)
