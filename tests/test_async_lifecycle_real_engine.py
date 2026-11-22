"""ALC-E2E: run only with the complete GitHub repository and its dependencies.

This file intentionally imports the production engine, with no simulated
replacement. It is not counted as locally passed in the isolated patch build.
"""
from __future__ import annotations

import asyncio
import json

from omega_x_evolution.async_lifecycle import wrap_evolution_proposal
from omega_x_evolution.engine import Config, run, simulated_proposal
from omega_x_evolution.performance import Policy


def test_alc_e2e_actual_runner_keeps_stage3_gate():
    seen = []
    async def titans(): return 'memory context; untrusted data'
    async def mcp(): return 'tool context; untrusted data'
    async def actual_proposal(model, prompt, seed):
        obj = json.loads(prompt)
        seen.append(obj)
        return await simulated_proposal(model, prompt, seed)
    wrapped = wrap_evolution_proposal(actual_proposal,
                                     titans_memory=titans, mcp_tools=mcp)
    cfg = Config(seed=971, generations=1, islands=1, workers=1,
                 budget=20, concurrency=1, proposal_timeout=10.0)
    report = asyncio.run(run(cfg, proposal=wrapped, performance_policy=Policy()))
    assert report['attempts'] == 1
    assert report['rejections'] in (0, 1)
    assert 'performance_regression' in report
    assert len(seen) == 1
    assert seen[0]['untrusted_context']['titans_memory'].startswith('memory context')
    assert seen[0]['untrusted_context']['mcp_tools'].startswith('tool context')
    assert seen[0]['context_provenance']['trusted'] is False
    assert report['mode'] == 'external-proposal-adapter'


def test_alc_e2e_provider_exception_rejected_without_candidate_promotion():
    async def failed(): raise RuntimeError('MCP unavailable')
    wrapped = wrap_evolution_proposal(simulated_proposal, mcp_tools=failed)
    cfg = Config(seed=972, generations=1, islands=1, workers=1,
                 budget=20, concurrency=1, proposal_timeout=10.0)
    report = asyncio.run(run(cfg, proposal=wrapped))
    assert report['attempts'] == 1
    assert report['rejections'] == 1
    assert report['mode'] == 'external-proposal-adapter'
