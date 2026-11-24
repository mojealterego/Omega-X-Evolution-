"""Explicit opt-in adapter to Shinka's existing LLM clients; no agentic tools."""
from __future__ import annotations
import math


class ShinkaProposal:
    def __init__(self, models: dict[str,str], client_factory=None):
        if set(models) != {'fast','deep'} or any(not isinstance(m,str) or not m.strip() or m.lower().startswith('headless/') for m in models.values()):
            raise ValueError('two non-headless model names required')
        if client_factory is None:
            from shinka.llm import AsyncLLMClient
            client_factory=lambda model: AsyncLLMClient(model_names=model, max_tokens=512, verbose=False)
        self.clients={role:client_factory(model) for role,model in models.items()}
        self.reported_cost=0.

    async def __call__(self, role: str, prompt: str, seed: int) -> str:
        response=await self.clients[role].query(msg=prompt,system_msg='Return only a single exact SEARCH/REPLACE patch. No tools. Only bounded arithmetic expressions over x,y. No prose or code fences.')
        if response is None: raise ValueError('empty provider response')
        cost=getattr(response,'cost',0.)
        if isinstance(cost,(float,int)) and math.isfinite(cost) and cost>=0:self.reported_cost+=cost
        if getattr(response,'num_tool_calls',0) or not isinstance(response.content,str):raise ValueError('invalid provider response')
        return response.content


    @classmethod
    def from_omega_gateway(cls, client_factory=None):
        """Explicit local-only route, using the existing Shinka adapter."""
        model = "local/omega-local@http://127.0.0.1:8788/v1?api_key_env=OMEGA_GATEWAY_TOKEN"
        return cls({"fast": model, "deep": model}, client_factory=client_factory)
