import asyncio
from dataclasses import replace
import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context

import pytest
from shinka.omega.engine import Cascade, Config, run, BASELINE
from shinka.omega.checkpoint import CheckpointStore
from shinka.omega.workers import EvaluationInput, evaluate_one, evaluate_batch


def test_worker_returns_same_result_and_failure_deltas():
    c = Cascade(5)
    expected = [c.evaluate(s) for s in (BASELINE, 'x', 'x/0', '__import__("os")')]
    fresh = Cascade(5)
    inputs = [EvaluationInput(s, tuple(fresh.challenge), fresh.grid) for s in (BASELINE, 'x', 'x/0', '__import__("os")')]
    assert all(not hasattr(i, 'holdout') for i in inputs)
    results = asyncio.run(evaluate_batch(inputs, None))
    assert [r.result for r in results] == expected
    for p in fresh.challenge:
        assert sum(r.failed_points.count(p) for r in results) == c.failures[p]


def test_real_process_worker():
    c = Cascade(3)
    with ProcessPoolExecutor(max_workers=2, mp_context=get_context('spawn')) as pool:
        result = pool.submit(evaluate_one, EvaluationInput(BASELINE, tuple(c.challenge), c.grid)).result(timeout=15)
    assert result.pid != os.getpid()
    assert result.result == c.evaluate(BASELINE)


@pytest.mark.parametrize('seed', [5, 77])
def test_parallel_matches_serial(seed):
    cfg = Config(seed=seed, generations=4, islands=3, workers=3)
    assert asyncio.run(run(cfg, evaluation_processes=2)) == asyncio.run(run(cfg))


def test_resume_across_execution_backends(tmp_path):
    cfg = Config(seed=5, generations=4, islands=2, workers=2)
    store = CheckpointStore(tmp_path/'run.db', b'x'*32)
    asyncio.run(run(replace(cfg,generations=2), checkpoint=store))
    assert asyncio.run(run(cfg, checkpoint=store, resume=True, evaluation_processes=2)) == asyncio.run(run(cfg))


@pytest.mark.parametrize('value', [0, -1, 33, True])
def test_invalid_process_count(value):
    with pytest.raises(ValueError):
        asyncio.run(run(Config(), evaluation_processes=value))


def test_failed_worker_batch_preserves_last_commit(tmp_path, monkeypatch):
    from concurrent.futures.process import BrokenProcessPool
    from shinka.omega import engine
    cfg = Config(seed=5, generations=2, islands=2, workers=2)
    store = CheckpointStore(tmp_path/'run.db', b'x'*32)
    asyncio.run(run(cfg, checkpoint=store))
    before = store.load()
    original = engine.evaluate_batch
    async def fail_batch(jobs, executor):
        raise BrokenProcessPool('simulated worker loss')
    monkeypatch.setattr(engine, 'evaluate_batch', fail_batch)
    with pytest.raises(BrokenProcessPool):
        asyncio.run(run(replace(cfg,generations=3), checkpoint=store, resume=True))
    assert store.load() == before
    monkeypatch.setattr(engine, 'evaluate_batch', original)
    assert asyncio.run(run(replace(cfg,generations=3), checkpoint=store, resume=True)) == asyncio.run(run(replace(cfg,generations=3)))


def test_broken_process_pool_propagates_failure():
    from concurrent.futures.process import BrokenProcessPool
    c = Cascade(3)
    with ProcessPoolExecutor(max_workers=1, mp_context=get_context('spawn')) as pool:
        with pytest.raises(BrokenProcessPool):
            pool.submit(os._exit, 77).result(timeout=15)
        with pytest.raises(BrokenProcessPool):
            asyncio.run(evaluate_batch([EvaluationInput(BASELINE, tuple(c.challenge), c.grid)], pool))
