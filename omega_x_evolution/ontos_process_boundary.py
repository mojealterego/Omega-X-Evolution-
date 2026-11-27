"""Native two-process reference replay with bounded observation-only IPC.

The fixed spawned worker receives only sequential sensor frames. Evaluator
truth, seeds and rewards stay in the parent. This is data-flow separation,
not a security sandbox: both processes share an OS user and trusted code.
No arbitrary callbacks, executable payloads, or operational actions.
"""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import time

from .ontos_observation_policy import ObservationPolicy, SensorFrame
from .ontos_testbed import ScoredStep, _episode

MAX_FRAME = 1024
_ALLOWED = (0, 1, 2, 3, 5)


class BoundaryError(RuntimeError):
    """The finite observation-only IPC contract failed."""


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate JSON key')
        obj[key] = value
    return obj


def _constant(value):
    raise ValueError('non-finite JSON constant')


def _decode(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_FRAME:
        raise ValueError('frame size')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)


def _encode(obj):
    raw = json.dumps(obj, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_FRAME:
        raise ValueError('frame size')
    return raw


def _decode_frame(raw, seq):
    obj = _decode(raw)
    if (type(obj) is not dict or set(obj) != {'seq','discrete','continuous','damage'}
            or type(obj['seq']) is not int or obj['seq'] != seq
            or type(obj['continuous']) is not list):
        raise ValueError('sensor frame schema or sequence')
    return SensorFrame(obj['discrete'], tuple(obj['continuous']), obj['damage'])


def _decode_action(raw, seq):
    try:
        obj = _decode(raw)
        if (type(obj) is not dict or set(obj) != {'seq','action'}
                or type(obj['seq']) is not int or obj['seq'] != seq
                or type(obj['action']) is not int or obj['action'] not in _ALLOWED):
            raise ValueError('action frame schema or sequence')
        return obj['action']
    except (ValueError, TypeError, RecursionError) as exc:
        raise BoundaryError('invalid action frame') from exc


def _worker(connection):
    try:
        policy = ObservationPolicy()
        for seq in range(240):
            raw = connection.recv_bytes(MAX_FRAME)
            frame = _decode_frame(raw, seq)
            decision = policy.decide(frame)
            connection.send_bytes(_encode({'seq':seq,'action':decision.action}))
    except (EOFError, OSError, ValueError, TypeError, RecursionError):
        # Fail closed; the parent observes EOF and discards the whole episode.
        return
    finally:
        connection.close()


def _exchange(connection, frame, deadline):
    try:
        if deadline <= time.monotonic():
            raise BoundaryError('IPC timeout')
        connection.send_bytes(_encode(frame))
        if not connection.poll(max(0., deadline-time.monotonic())):
            raise BoundaryError('IPC timeout')
        raw = connection.recv_bytes(MAX_FRAME)
        if time.monotonic() > deadline:
            raise BoundaryError('IPC timeout')
        return _decode_action(raw, frame['seq'])
    except (EOFError, OSError, ValueError, TypeError) as exc:
        raise BoundaryError('worker communication failed') from exc


def run_isolated_episode(seed: int, *, horizon: int = 240,
                         timeout: float = 10.) -> tuple[ScoredStep, ...]:
    """Replay the unchanged reference policy in a spawned process.

    One deadline covers IPC exchanges and normal worker exit. The trusted
    worker emits only small complete frames; the timeout is not a guarantee
    against an adversarial partial pipe write or an unresponsive OS. Spawn
    requires a normal importable Python entrypoint (guard scripts with main).
    Any protocol/timeout failure discards the episode and stops the worker.
    """
    if (type(seed) is not int or not 0 <= seed < 2**32
            or type(horizon) is not int or not 1 <= horizon <= 240
            or type(timeout) not in (int,float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ValueError('bounded episode and timeout')
    context = mp.get_context('spawn')
    parent, child = context.Pipe()
    process = context.Process(target=_worker, args=(child,), daemon=True)
    sim = _episode(seed,horizon)
    deadline = time.monotonic()+timeout
    started = False
    try:
        process.start(); started = True; child.close()
        observation = next(sim)
        for seq in range(horizon):
            action = _exchange(parent, {'seq':seq,'discrete':observation.discrete,
                               'continuous':list(observation.continuous),'damage':observation.damage}, deadline)
            try:
                observation = sim.send(action)
            except StopIteration as stop:
                result = stop.value
                break
        else:
            raise BoundaryError('simulator did not terminate')
        if len(result) != horizon:
            raise BoundaryError('incomplete episode')
        parent.close()
        process.join(max(0., deadline-time.monotonic()))
        if process.is_alive() or process.exitcode != 0 or time.monotonic() > deadline:
            raise BoundaryError('worker did not exit normally before timeout')
        return result
    finally:
        sim.close(); parent.close(); child.close()
        if started:
            if process.is_alive():
                process.terminate(); process.join(1.)
            if process.is_alive():
                process.kill(); process.join(1.)
            if process.is_alive():
                raise BoundaryError('worker cleanup failed')
        process.close()
