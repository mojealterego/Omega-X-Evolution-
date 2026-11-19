"""Bounded inference routing for existing OMEGA MLPs. Hardware is never simulated implicitly."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import threading
from typing import Protocol

import numpy as np

from .neural import Model, predict, _array

KINDS = ('cpu', 'gpu', 'npu')
DEFAULT_CAP = 64 * 1024 * 1024


class ComputeError(RuntimeError):
    """No admissible device produced a verified result."""


@dataclass(frozen=True)
class Device:
    name: str
    kind: str
    memory: int
    physical: bool

    def __post_init__(self):
        if (not isinstance(self.name, str) or not self.name or len(self.name)>128 or
            self.kind not in KINDS or type(self.memory) is not int or self.memory<1 or
            type(self.physical) is not bool):
            raise ValueError('invalid device')


class Backend(Protocol):
    device: Device
    def infer(self, model: Model, rows) -> np.ndarray: ...


class CPUBackend:
    device = Device('cpu', 'cpu', DEFAULT_CAP, True)

    def infer(self, model, rows):
        return predict(model, rows)


class TorchBackend:
    """Trusted installed PyTorch runtime; CPU reference remains the acceptance oracle."""
    def __init__(self, torch, device, target, dtype):
        self.device=device; self._torch=torch; self._target=target; self._dtype=dtype

    def infer(self, model, rows):
        torch=self._torch
        x,_=_array(rows)
        with torch.inference_mode():
            a=torch.tensor(x,device=self._target,dtype=self._dtype)
            for i,(w,b) in enumerate(zip(model.weights,model.biases)):
                a=a@torch.tensor(w,device=self._target,dtype=self._dtype)+torch.tensor(b,device=self._target,dtype=self._dtype)
                if i<len(model.weights)-1:
                    a=torch.tanh(a) if model.architecture.activation=='tanh' else torch.relu(a)
            return (a*model.scale).detach().cpu().numpy().astype(np.float64)


def probe(*, enable_torch=False, enable_npu=False, enable_qnn=False):
    """Return usable runtime devices. memory is an admission cap, not reserved VRAM."""
    if type(enable_torch) is not bool or type(enable_npu) is not bool or type(enable_qnn) is not bool or (enable_npu and not enable_torch):
        raise ValueError('NPU requires explicit Torch opt-in')
    devices: list[Backend]=[CPUBackend()]
    if enable_qnn:
        from .qnn import QNNBackend, QNNUnavailable
        try: devices.append(QNNBackend())
        except QNNUnavailable: pass
    if not enable_torch: return devices
    try:
        import torch
    except (ImportError,OSError): return devices
    try:
        if torch.cuda.is_available():
            for i in range(min(torch.cuda.device_count(),16)):
                free,_=torch.cuda.mem_get_info(i)
                if free>0:
                    name=f'cuda:{i}'
                    devices.append(TorchBackend(torch,Device(name,'gpu',min(int(free),DEFAULT_CAP),True),name,torch.float64))
    except (RuntimeError,OSError,AttributeError): pass
    try:
        if torch.backends.mps.is_available():
            free=torch.mps.recommended_max_memory()-torch.mps.current_allocated_memory()
            if free>0:
                devices.append(TorchBackend(torch,Device('mps','gpu',min(int(free),DEFAULT_CAP),True),'mps',torch.float32))
    except (RuntimeError,OSError,AttributeError): pass
    if enable_npu:
        try:
            import torch_npu  # noqa: F401 -- trusted operator-installed extension
            if torch.npu.is_available():
                for i in range(min(torch.npu.device_count(),16)):
                    free,_=torch.npu.mem_get_info(i)
                    if free>0:
                        name=f'npu:{i}'
                        devices.append(TorchBackend(torch,Device(name,'npu',min(int(free),DEFAULT_CAP),True),name,torch.float32))
        except (ImportError,RuntimeError,OSError,AttributeError): pass
    return devices


@dataclass(frozen=True)
class Inference:
    device: str
    physical: bool
    values: np.ndarray
    attempts: tuple[str,...]
    failures: tuple[tuple[str,str],...]
    estimated_bytes: int


class Router:
    """Thread-safe admission leases; strict preferences or explicit fallback.

    CPU comparison is mandatory, including for accelerator results. The cap is
    a conservative tensor-workspace proxy; it is not an OS/device memory limit.
    No caller-provided code, device strings or flags reach the runtime.
    """
    def __init__(self, backends, *, memory_cap=DEFAULT_CAP):
        self._backends=tuple(backends)
        if (not 1<=len(self._backends)<=33 or any(not isinstance(b.device,Device) for b in self._backends) or
            len({b.device.name for b in self._backends})!=len(self._backends) or
            type(memory_cap) is not int or not 1<=memory_cap<=2**40):
            raise ValueError('invalid backend inventory or cap')
        self._cap=memory_cap; self._lock=threading.Lock(); self._reserved=0; self._busy=set()

    @property
    def reserved(self):
        with self._lock: return self._reserved

    def infer(self, model, rows, *, prefer=('npu','gpu','cpu')):
        if not isinstance(model,Model): raise ValueError('invalid model')
        if type(prefer) is not tuple or not prefer or len(set(prefer))!=len(prefer) or any(k not in KINDS for k in prefer):
            raise ValueError('invalid device preference')
        _array(rows)  # existing domain and record bounds
        estimate=8*(model.architecture.parameters+len(rows)*(2+sum(model.architecture.hidden)+1))*4
        attempts=[]; failures=[]
        for kind in prefer:
            for backend in self._backends:
                d=backend.device
                if d.kind!=kind: continue
                with self._lock:
                    if d.name in self._busy or estimate>d.memory or self._reserved+estimate>self._cap:
                        failures.append((d.name,'admission rejected')); continue
                    self._busy.add(d.name);self._reserved+=estimate
                attempts.append(d.name)
                try:
                    reference=predict(model,rows)
                    values=backend.infer(model,rows)
                    if (not isinstance(values,np.ndarray) or values.shape!=reference.shape or not np.isfinite(values).all() or
                        not np.allclose(values,reference,rtol=1e-5,atol=1e-7)):
                        raise ComputeError('reference mismatch')
                    values=np.array(values,dtype=np.float64,copy=True); values.setflags(write=False)
                    return Inference(d.name,d.physical,values,tuple(attempts),tuple(failures),estimate)
                except (RuntimeError,MemoryError,OSError,ValueError) as exc:
                    failures.append((d.name,type(exc).__name__))
                finally:
                    with self._lock:
                        self._busy.remove(d.name);self._reserved-=estimate
        raise ComputeError(f'no verified device: {failures!r}')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--torch',action='store_true');p.add_argument('--npu',action='store_true');p.add_argument('--qnn',action='store_true');p.add_argument('--demo',action='store_true');a=p.parse_args()
    backends=probe(enable_torch=a.torch,enable_npu=a.npu,enable_qnn=a.qnn)
    report={'devices':[asdict(b.device) for b in backends]}
    if a.demo:
        from .neural import BASELINE,fit
        from .neuro_symbolic import fixture
        data=fixture('xor');model=fit(BASELINE,data.train,epochs=20)
        r=Router(backends).infer(model,data.test)
        report['inference']={'device':r.device,'physical':r.physical,'attempts':r.attempts,'failures':r.failures,'estimated_bytes':r.estimated_bytes,'samples':len(r.values),'reference_verified':True}
    print(json.dumps(report,indent=2,allow_nan=False))


if __name__=='__main__': main()
