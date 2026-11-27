"""Hermetic exec bootstrap for the native ONTOS reference sandbox.

Trusted supervisor provisions distinct numeric Linux identities. This is not
an authentication service: resolve tenant only after upstream authorization.
Trusted interpreter, system dependencies and immutable package deployment are
required. No inherited environment or application FDs, no fallback to spawn.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time

from .ontos_sandbox import SandboxError, _exchange, _receive, _worker
from .ontos_testbed import ScoredStep, _episode

_ENV = {'HOME':'/nonexistent','LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
        'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z',re.ASCII)
_BOOT = ('import sys;sys.path.insert(0,sys.argv[1]);'
         'from omega_x_evolution.ontos_exec_boundary import _bootstrap;'
         '_bootstrap(int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]))')


@dataclass(frozen=True, slots=True)
class Identity:
    tenant: str
    uid: int
    gid: int

    def __post_init__(self):
        if (type(self.tenant) is not str or not _NAME.fullmatch(self.tenant)
                or any(type(x) is not int or not 10000 <= x <= 2**31-2 or x == 65534
                       for x in (self.uid,self.gid))):
            raise ValueError('invalid dedicated tenant identity')


@dataclass(frozen=True, slots=True)
class TenantRegistry:
    identities: tuple[Identity,...]

    def __post_init__(self):
        if (type(self.identities) is not tuple or not 1 <= len(self.identities) <= 128
                or any(type(x) is not Identity for x in self.identities)):
            raise ValueError('bounded identity registry required')
        for identity in self.identities:
            identity.__post_init__()
        for field in ('tenant','uid','gid'):
            if len({getattr(x,field) for x in self.identities}) != len(self.identities):
                raise ValueError('tenant identity alias')

    def resolve(self, tenant: str) -> Identity:
        self.__post_init__()
        for identity in self.identities:
            if type(tenant) is str and identity.tenant == tenant:
                return identity
        raise SandboxError('tenant not provisioned')


def _bootstrap(fd: int, uid: int, gid: int) -> None:
    # Called only by the fixed isolated interpreter entrypoint, before ready.
    if (os.getresuid() != (uid,)*3 or os.getresgid() != (gid,)*3
            or os.getgroups() or dict(os.environ) != _ENV or os.getcwd() != '/'):
        raise SandboxError('unexpected bootstrap identity or environment')
    live = set()
    for entry in os.listdir('/proc/self/fd'):
        n = int(entry)
        try:
            os.fstat(n)
        except OSError as exc:
            import errno
            if exc.errno != errno.EBADF:
                raise
        else:
            live.add(n)
    if fd < 3 or live != {0,1,2,fd}:
        raise SandboxError('unexpected inherited descriptors')
    with socket.socket(fileno=fd) as channel:
        if channel.family != socket.AF_UNIX or channel.type != socket.SOCK_SEQPACKET:
            raise SandboxError('unexpected channel type')
        _worker(channel)


def _launch(identity: Identity):
    if type(identity) is not Identity:
        raise ValueError('typed identity required')
    identity.__post_init__()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64' or os.geteuid() != 0:
        raise SandboxError('privileged Linux x86_64 supervisor required')
    root = str(Path(__file__).resolve().parent.parent)
    executable = str(Path(sys.executable).resolve(strict=True))
    a,b = socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    a.setblocking(False)
    try:
        p = subprocess.Popen([executable,'-I','-B','-c',_BOOT,root,str(b.fileno()),
                              str(identity.uid),str(identity.gid)],
                             cwd='/',env=dict(_ENV),user=identity.uid,group=identity.gid,
                             extra_groups=(),umask=0o077,close_fds=True,pass_fds=(b.fileno(),),
                             stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except BaseException:
        a.close()
        raise
    finally:
        b.close()
    return a,p


def _stop(channel, process):
    channel.close()
    try:
        process.wait(timeout=1.)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1.)


def run_exec_episode(registry: TenantRegistry, tenant: str, seed: int, *,
                     horizon: int = 240, timeout: float = 10.) -> tuple[ScoredStep,...]:
    """Run reference policy via sanitized exec and the existing seccomp filter."""
    if (type(registry) is not TenantRegistry or type(seed) is not int or not 0 <= seed < 2**32
            or type(horizon) is not int or not 1 <= horizon <= 240
            or type(timeout) not in (int,float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ValueError('bounded exec episode')
    identity = registry.resolve(tenant)
    deadline = time.monotonic()+timeout
    channel,process = _launch(identity)
    sim = _episode(seed,horizon)
    try:
        if _receive(channel,deadline) != b'{"ready":1}':
            raise SandboxError('exec bootstrap not ready')
        obs = next(sim)
        for seq in range(horizon):
            action = _exchange(channel,{'seq':seq,'discrete':obs.discrete,
                'continuous':list(obs.continuous),'damage':obs.damage},deadline)
            try:
                obs = sim.send(action)
            except StopIteration as stop:
                result = stop.value
                break
        else:
            raise SandboxError('incomplete simulator trace')
        channel.close()
        try:
            code = process.wait(timeout=max(0.,deadline-time.monotonic()))
        except subprocess.TimeoutExpired as exc:
            raise SandboxError('exec worker deadline') from exc
        if code != 0 or len(result) != horizon or time.monotonic() > deadline:
            raise SandboxError('exec worker did not complete normally')
        return result
    finally:
        sim.close()
        _stop(channel,process)
