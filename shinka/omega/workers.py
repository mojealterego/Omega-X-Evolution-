"""Trusted local evaluation workers. The bounded AST interpreter is the only
candidate execution path; process separation is not an OS security sandbox.
No holdout or checkpoint key is sent in the evaluation payload.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import Executor
from dataclasses import dataclass
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import Result

Point = tuple[float, float]


@dataclass(frozen=True)
class EvaluationInput:
    code: str
    challenge: tuple[Point, ...]
    grid: tuple[Point, ...]


@dataclass(frozen=True)
class EvaluationOutput:
    result: Result
    failed_points: tuple[Point, ...]
    pid: int


def evaluate_one(job: EvaluationInput) -> EvaluationOutput:
    from .engine import Cascade
    # Local scratch state only: failures are commutative increments, and neither
    # the archive nor the held-out dataset participates in candidate evaluation.
    cascade = Cascade.__new__(Cascade)
    cascade.challenge = list(job.challenge)
    cascade.grid = job.grid
    cascade.failures = dict.fromkeys(job.challenge, 0)
    result = cascade.evaluate(job.code)
    failed = tuple(p for p in job.challenge if cascade.failures[p])
    return EvaluationOutput(result, failed, os.getpid())


async def evaluate_batch(jobs: list[EvaluationInput], executor: Executor | None) -> list[EvaluationOutput]:
    if executor is None:
        return [evaluate_one(job) for job in jobs]
    loop = asyncio.get_running_loop()
    # gather preserves input order. Worker failure propagates to coordinator;
    # caller must not commit any generation result until the whole batch returns.
    return list(await asyncio.gather(*(loop.run_in_executor(executor, evaluate_one, job) for job in jobs)))
