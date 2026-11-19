import numpy as np
import pytest
from omega_x_evolution.compute import Device, Router, CPUBackend, probe, ComputeError
from omega_x_evolution.neural import BASELINE, fit, predict
from omega_x_evolution.neuro_symbolic import fixture


def test_real_cpu_inference():
    data=fixture('xor',seed=13); model=fit(BASELINE,data.train,epochs=5)
    r=Router([CPUBackend()]).infer(model,data.test)
    assert r.device=='cpu' and np.array_equal(r.values,predict(model,data.test))
    assert r.attempts==('cpu',)
    assert any(b.device.kind=='cpu' for b in probe())


class SimGPU:
    device=Device('gpu:test','gpu',1024*1024,False)
    def __init__(self, mode): self.mode=mode
    def infer(self,m,rows):
        if self.mode=='fail': raise RuntimeError('device lost')
        return predict(m,rows)+(1 if self.mode=='bad' else 0)


@pytest.mark.parametrize('mode',['fail','bad'])
def test_fallback_and_strict_policy(mode):
    d=fixture('xor'); m=fit(BASELINE,d.train,epochs=2)
    router=Router([CPUBackend(),SimGPU(mode)])
    r=router.infer(m,d.test,prefer=('gpu','cpu'))
    assert r.device=='cpu' and r.attempts==('gpu:test','cpu') and len(r.failures)==1
    assert router.reserved==0
    with pytest.raises(ComputeError): router.infer(m,d.test,prefer=('gpu',))
    assert router.reserved==0


def test_caps_and_simulated_device_not_hardware():
    d=fixture('xor'); m=fit(BASELINE,d.train,epochs=2)
    g=SimGPU('ok'); router=Router([g,CPUBackend()],memory_cap=65536)
    r=router.infer(m,d.test,prefer=('gpu','cpu'))
    assert r.device=='gpu:test' and not r.physical
    with pytest.raises(ComputeError): Router([CPUBackend()],memory_cap=1).infer(m,d.test)
    with pytest.raises(ValueError): Router([g,g])
    with pytest.raises(ValueError): router.infer(m,d.test,prefer=('shell',))


def test_concurrent_reservations_do_not_overcommit():
    import threading
    from concurrent.futures import ThreadPoolExecutor
    ready=threading.Event(); release=threading.Event()
    d=fixture('xor'); m=fit(BASELINE,d.train,epochs=2)
    class BlockingCPU(CPUBackend):
        def infer(self,model,rows):
            ready.set()
            if not release.wait(5): raise RuntimeError('test wait timeout')
            return super().infer(model,rows)
    router=Router([BlockingCPU()])
    with ThreadPoolExecutor(1) as pool:
        first=pool.submit(router.infer,m,d.test)
        try:
            assert ready.wait(5) and router.reserved>0
            with pytest.raises(ComputeError): router.infer(m,d.test)
        finally: release.set()
        assert first.result(timeout=5).device=='cpu'
    assert router.reserved==0


def test_torch_cpu_adapter_real_tensor_execution():
    import importlib.util
    import subprocess
    import sys
    if importlib.util.find_spec('torch') is None: pytest.skip('optional torch not installed')
    # Never initialize Torch threads in the parent of later fork-based tests.
    code = """
import torch
import numpy as np
from omega_x_evolution.compute import TorchBackend, Device, Router
from omega_x_evolution.neural import BASELINE, fit, predict
from omega_x_evolution.neuro_symbolic import fixture
d=fixture('xor');m=fit(BASELINE,d.train,epochs=2)
backend=TorchBackend(torch,Device('torch:cpu','cpu',1048576,True),'cpu',torch.float64)
r=Router([backend]).infer(m,d.test)
assert r.device=='torch:cpu' and np.allclose(r.values,predict(m,d.test),rtol=1e-12,atol=1e-12)
"""
    subprocess.run([sys.executable,'-c',code],check=True,timeout=40)
