import asyncio
from types import SimpleNamespace
from omega_x_evolution.providers import ShinkaProposal


def test_gateway_factory_uses_existing_local_provider():
    names = []

    class Client:
        async def query(self, **kwargs):
            assert "No tools" in kwargs["system_msg"]
            return SimpleNamespace(content="patch", cost=0, num_tool_calls=0)

    def factory(name):
        names.append(name)
        return Client()

    proposal = ShinkaProposal.from_omega_gateway(client_factory=factory)
    assert names == [
        "local/omega-local@http://127.0.0.1:8788/v1?api_key_env=OMEGA_GATEWAY_TOKEN"
    ] * 2
    assert asyncio.run(proposal("fast", "request", 0)) == "patch"
    assert proposal.reported_cost == 0
