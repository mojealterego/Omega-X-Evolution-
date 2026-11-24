# Local-only OMEGA Gateway provider
Instantiate ShinkaProposal.from_omega_gateway() from omega_x_evolution.providers.
Requires a running gateway on 127.0.0.1:8788 and the private OMEGA_GATEWAY_TOKEN
environment variable. Uses the existing Shinka client; no cloud fallback and no
tools. Does not authorize RSI, changes to acceptance gates, or model execution
without the existing engine policy. Test: pytest -q tests/test_omega_gateway_provider.py.
Source tests unexecuted; native end-to-end not verified.
