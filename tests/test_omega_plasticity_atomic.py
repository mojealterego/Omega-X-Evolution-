"""Regression: reference retention measurement must be failure atomic."""
import pytest
from omega_x_evolution import llm_plasticity, plasticity


def test_reference_evaluation_failure_preserves_active_adapter(monkeypatch):
    import torch
    torch.set_num_threads(1)
    session=llm_plasticity.tiny_decoder()
    with torch.no_grad():
        for p in session.params.values(): p.add_(0.01)
    active=session.snapshot()
    assert active != session.initial
    train,validation,retention,_=plasticity.fixture(42,groups=4)
    original=session._mean_loss
    def fail_at_reference(data):
        if session.snapshot() == session.initial:
            raise RuntimeError('injected reference evaluation failure')
        return original(data)
    monkeypatch.setattr(session,'_mean_loss',fail_at_reference)
    with pytest.raises(RuntimeError,match='injected reference'):
        session.fit(train[:4],validation[:4],retention[:4],steps=1)
    assert session.snapshot() == active
    assert session.base_digest() == session.base_sha
