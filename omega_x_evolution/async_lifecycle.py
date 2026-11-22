"""Bounded asynchronous I/O context for the existing OMEGA-X Proposal hook.

Sources are caller-supplied, zero-argument async producers. Nothing in this
module fetches private data, grants tools, changes evaluator gates, or executes
source content. Sources run concurrently; their outputs are explicitly labeled
untrusted JSON values. The runner retains its existing Proposal interface.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import json
import math
from typing import Awaitable, Callable

SCHEMA = 'omega-async-life-cycle-v1'
_SOURCE_ORDER = ('active_inference', 'titans_memory', 'mcp_tools')
Producer = Callable[[], Awaitable[str]]
Proposal = Callable[[str, str, int], Awaitable[str]]


class AsyncPhaseError(RuntimeError):
    """Controlled error surface: never forward exception text or tool output."""

    def __init__(self, phase: str, reason: str) -> None:
        self.phase = phase
        self.reason = reason
        super().__init__(f'{phase}: {reason}')


@dataclass(frozen=True, slots=True)
class AsyncLifecycleConfig:
    timeout_s: float = 30.0
    max_context_bytes: int = 8192
    prompt_limit_bytes: int = 131072

    def __post_init__(self) -> None:
        if (type(self.timeout_s) not in (int, float)
                or not math.isfinite(self.timeout_s)
                or not 0 < self.timeout_s <= 300):
            raise ValueError('timeout must be finite and between 0 and 300 seconds')
        if (type(self.max_context_bytes) is not int
                or not 1024 <= self.max_context_bytes <= 65536):
            raise ValueError('bounded UTF-8 context budget required')
        if (type(self.prompt_limit_bytes) is not int
                or not 1024 <= self.prompt_limit_bytes <= 1_048_576):
            raise ValueError('bounded UTF-8 prompt budget required')


async def _source(name: str, producer: Producer) -> str:
    try:
        result = producer()
    except Exception as exc:
        raise AsyncPhaseError(name, 'PROVIDER_FAILED') from None
    if not inspect.isawaitable(result):
        raise AsyncPhaseError(name, 'INVALID_PROVIDER')
    try:
        value = await result
    except Exception as exc:
        raise AsyncPhaseError(name, 'PROVIDER_FAILED') from None
    if type(value) is not str:
        raise AsyncPhaseError(name, 'INVALID_RESPONSE')
    return value


async def collect_lifecycle_context(*, active_inference: Producer | None = None,
                                    titans_memory: Producer | None = None,
                                    mcp_tools: Producer | None = None,
                                    config: AsyncLifecycleConfig | None = None) -> dict[str, str]:
    """Concurrent I/O with one wall-clock deadline, strict failure and bounded bytes.

    A provider MUST cooperate with asyncio cancellation. Non-cooperative or
    untrusted native calls need a separate isolated worker/process; cancellation
    cannot forcibly stop such code. No retries occur automatically.
    """
    cfg = config if config is not None else AsyncLifecycleConfig()
    if type(cfg) is not AsyncLifecycleConfig:
        raise ValueError('typed config required')
    cfg.__post_init__()
    sources = dict(zip(_SOURCE_ORDER, (active_inference, titans_memory, mcp_tools)))
    active = [(name, fn) for name, fn in sources.items() if fn is not None]
    if any(not callable(fn) for _, fn in active):
        raise ValueError('producers must be callable')
    if not active:
        return {}
    tasks = {name: asyncio.create_task(_source(name, fn)) for name, fn in active}
    try:
        done, pending = await asyncio.wait(tasks.values(), timeout=cfg.timeout_s,
                                           return_when=asyncio.FIRST_EXCEPTION)
        # Stable failure precedence independent of task completion order.
        for name, task in tasks.items():
            if task in done:
                if task.cancelled():
                    raise AsyncPhaseError(name, 'PROVIDER_CANCELLED')
                err = task.exception()
                if err is not None:
                    if isinstance(err, AsyncPhaseError):
                        raise err
                    raise AsyncPhaseError(name, 'PROVIDER_FAILED') from err
        if pending:
            raise AsyncPhaseError('lifecycle', 'TIMEOUT')
        output = {name: tasks[name].result() for name, _ in active}
        if sum(len(value.encode('utf-8')) for value in output.values()) > cfg.max_context_bytes:
            raise AsyncPhaseError('lifecycle', 'CONTEXT_TOO_LARGE')
        return output
    finally:
        unfinished = [task for task in tasks.values() if not task.done()]
        for task in unfinished:
            task.cancel()
        if unfinished:
            # Cancellation is cooperative. Keep the controller responsive even
            # when a broken adapter ignores CancelledError.
            await asyncio.wait(unfinished, timeout=0.2)
        for task in tasks.values():
            if task.done() and not task.cancelled():
                task.exception()  # consume exceptions from sibling tasks


def wrap_evolution_proposal(proposal: Proposal, *,
                            active_inference: Producer | None = None,
                            titans_memory: Producer | None = None,
                            mcp_tools: Producer | None = None,
                            config: AsyncLifecycleConfig | None = None) -> Proposal:
    """Optional adapter: pass directly as ``engine.run(..., proposal=wrapped)``.

    The original prompt is *never* sent to a provider by this adapter. A source
    is a zero-argument closure so any data disclosure must be an explicit
    operator decision in the closure's implementation. Untrusted output stays
    an isolated JSON field; LLM prompt-injection defenses remain necessary.
    """
    if not callable(proposal):
        raise ValueError('callable Proposal required')
    cfg = config if config is not None else AsyncLifecycleConfig()
    if type(cfg) is not AsyncLifecycleConfig:
        raise ValueError('typed config required')
    cfg.__post_init__()
    if any(x is not None and not callable(x) for x in (active_inference, titans_memory, mcp_tools)):
        raise ValueError('callable async producers required')
    enabled = any(x is not None for x in (active_inference, titans_memory, mcp_tools))

    async def wrapped(model: str, prompt: str, seed: int) -> str:
        if not enabled:
            value = await proposal(model, prompt, seed)
        else:
            if type(prompt) is not str or len(prompt.encode('utf-8')) > cfg.prompt_limit_bytes:
                raise AsyncPhaseError('lifecycle', 'INVALID_PROMPT')
            try:
                original = json.loads(prompt)
            except (ValueError, TypeError) as exc:
                raise AsyncPhaseError('lifecycle', 'INVALID_PROMPT') from exc
            if (type(original) is not dict or type(original.get('parent')) is not str
                    or type(original.get('contract')) is not str
                    or 'untrusted_context' in original
                    or 'context_provenance' in original):
                raise AsyncPhaseError('lifecycle', 'INVALID_PROMPT')
            payload = await collect_lifecycle_context(
                active_inference=active_inference, titans_memory=titans_memory,
                mcp_tools=mcp_tools, config=cfg)
            original['untrusted_context'] = payload
            original['context_provenance'] = {
                'schema': SCHEMA, 'trusted': False, 'sources': list(payload),
            }
            wire = json.dumps(original, ensure_ascii=True, sort_keys=True,
                              separators=(',', ':'), allow_nan=False)
            if len(wire.encode('utf-8')) > cfg.prompt_limit_bytes + 2 * cfg.max_context_bytes:
                raise AsyncPhaseError('lifecycle', 'INVALID_PROMPT')
            value = await proposal(model, wire, seed)
        if type(value) is not str:
            raise AsyncPhaseError('proposal', 'INVALID_PROPOSAL')
        return value

    return wrapped
