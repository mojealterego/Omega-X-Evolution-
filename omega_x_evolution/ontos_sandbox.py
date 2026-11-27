"""Linux reference worker confinement: default-deny seccomp and packet IPC.

Trusted spawn/import bootstrap precedes confinement. No filesystem opens,
new sockets, executable mappings, process creation, signals or arbitrary FD
I/O after the filter. No claim of isolation from a hostile kernel or parent.
Linux x86_64 only; unsupported environments fail closed without fallback.
"""
from __future__ import annotations

import ctypes as C
import errno
import math
import multiprocessing as mp
import os
import platform
import select
import socket
import time

from .ontos_observation_policy import ObservationPolicy
from .ontos_process_boundary import MAX_FRAME, _decode_frame, _decode_action, _encode, BoundaryError
from .ontos_testbed import ScoredStep, _episode


class SandboxError(BoundaryError):
    """Sandbox initialization, protocol or deadline failure."""


class _Compare(C.Structure):
    _fields_ = [('arg', C.c_uint), ('op', C.c_int), ('a', C.c_uint64), ('b', C.c_uint64)]


_ALLOW = 0x7fff0000
_ERRNO = 0x00050000 | errno.EPERM
_EQ = 4
_MASKED_EQ = 7
_TSYNC = 4
MAX_ADDRESS_SPACE = 1024 * 1024 * 1024
MAX_CPU_SECONDS = 10


class _CapHeader(C.Structure):
    _fields_ = [('version', C.c_uint32), ('pid', C.c_int)]


class _CapData(C.Structure):
    _fields_ = [('effective', C.c_uint32), ('permitted', C.c_uint32), ('inheritable', C.c_uint32)]


def _limit_resources():
    import resource
    for kind, limit in ((resource.RLIMIT_AS, MAX_ADDRESS_SPACE),
                        (resource.RLIMIT_CPU, MAX_CPU_SECONDS), (resource.RLIMIT_CORE, 0)):
        soft,hard = resource.getrlimit(kind)
        cap = min(x for x in (limit,soft,hard) if x != resource.RLIM_INFINITY)
        resource.setrlimit(kind,(cap,cap))


def _drop_privilege():
    libc = C.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise SandboxError('no_new_privs failed')
    if os.geteuid() == 0:
        os.setgroups([]); os.setresgid(65534,65534,65534); os.setresuid(65534,65534,65534)
    if 0 in os.getresuid():
        raise SandboxError('root identity retained')
    if libc.prctl(47, 4, 0, 0, 0) != 0:  # PR_CAP_AMBIENT_CLEAR_ALL
        raise SandboxError('ambient capability clear failed')
    header = _CapHeader(0x20080522,0)
    data = (_CapData*2)()
    libc.capset.argtypes = [C.POINTER(_CapHeader), C.POINTER(_CapData)]
    libc.capget.argtypes = [C.POINTER(_CapHeader), C.POINTER(_CapData)]
    if libc.capset(C.byref(header),data) != 0 or libc.capget(C.byref(header),data) != 0:
        raise SandboxError('capability clear failed')
    if any(x.effective or x.permitted or x.inheritable for x in data):
        raise SandboxError('capabilities retained')
    # capset is thread-local. Verify trusted bootstrap threads before TSYNC.
    for tid in os.listdir('/proc/self/task'):
        with open('/proc/self/task/'+tid+'/status',encoding='ascii') as stream:
            status=dict(line.split(':',1) for line in stream if ':' in line)
        if (0 in map(int,status['Uid'].split()) or any(int(status[k],16) for k in ('CapEff','CapPrm','CapInh','CapAmb'))):
            raise SandboxError('bootstrap thread retains privileges')
    if libc.prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
        raise SandboxError('dumpability disable failed')


def install_filter(fd: int) -> None:
    """Irreversible confinement; call only inside a dedicated trusted worker.

    All threads receive the filter. If started as root, permanently drop to
    uid/gid 65534 before filtering. Only the designated socket may do I/O.
    A non-root launch does not create a separate OS identity. No fallback.
    """
    if (platform.system() != 'Linux' or platform.machine() != 'x86_64'
            or type(fd) is not int or fd < 3):
        raise SandboxError('unsupported sandbox platform or descriptor')
    try:
        lib = C.CDLL('libseccomp.so.2', use_errno=True)
        lib.seccomp_init.argtypes = [C.c_uint32]
        lib.seccomp_init.restype = C.c_void_p
        lib.seccomp_release.argtypes = [C.c_void_p]
        lib.seccomp_attr_set.argtypes = [C.c_void_p, C.c_int, C.c_uint32]
        lib.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
        lib.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint, C.POINTER(_Compare)]
        lib.seccomp_load.argtypes = [C.c_void_p]
        ctx = lib.seccomp_init(_ERRNO)
        if not ctx:
            raise SandboxError('seccomp initialization failed')
        try:
            def rule(name, *comparisons):
                nr = lib.seccomp_syscall_resolve_name(name.encode('ascii'))
                args = (_Compare * len(comparisons))(*comparisons)
                if nr < 0 or lib.seccomp_rule_add_array(ctx, _ALLOW, nr, len(args), args) != 0:
                    raise SandboxError('seccomp rule failed: ' + name)
            if lib.seccomp_attr_set(ctx, _TSYNC, 1) != 0:
                raise SandboxError('seccomp thread synchronization unavailable')
            for name in ('brk','munmap','mremap','madvise','futex','clock_gettime',
                         'getpid','gettid','getuid','geteuid','getgid','getegid',
                         'rt_sigaction','rt_sigprocmask','rt_sigreturn','exit','exit_group',
                         'close','sched_yield','getrandom','sigaltstack'):
                rule(name)
            for name in ('read','write','recvfrom','sendto'):
                rule(name, _Compare(0, _EQ, fd, 0))
            # Anonymous non-executable allocations only; no file-backed mmap.
            rule('mmap', _Compare(2, _MASKED_EQ, 4, 0), _Compare(3, _MASKED_EQ, 0x20, 0x20))
            _limit_resources()
            _drop_privilege()
            if lib.seccomp_load(ctx) != 0:
                raise SandboxError('seccomp load failed')
        finally:
            lib.seccomp_release(ctx)
    except OSError as exc:
        raise SandboxError('sandbox setup failed') from exc


def _worker(channel):
    try:
        install_filter(channel.fileno())
        policy = ObservationPolicy()
        channel.send(b'{"ready":1}')
        for seq in range(240):
            raw = channel.recv(MAX_FRAME+1)
            if not raw:
                return
            frame = _decode_frame(raw, seq)
            reply = _encode({'seq':seq,'action':policy.decide(frame).action})
            if channel.send(reply) != len(reply):
                return
    except (OSError, ValueError, TypeError, RecursionError, SandboxError):
        return
    finally:
        channel.close()


def _wait(channel, deadline, *, writing=False):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise SandboxError('sandbox IPC timeout')
    poller=select.poll()
    poller.register(channel,select.POLLOUT if writing else select.POLLIN)
    if not poller.poll(math.ceil(remaining*1000)) or time.monotonic() > deadline:
        raise SandboxError('sandbox IPC timeout')


def _receive(channel, deadline):
    try:
        while True:
            _wait(channel,deadline)
            try:
                raw = channel.recv(MAX_FRAME+1)
            except BlockingIOError:
                continue
            if not 1 <= len(raw) <= MAX_FRAME:
                raise SandboxError('closed or oversized sandbox packet')
            return raw
    except OSError as exc:
        raise SandboxError('sandbox IPC receive failed') from exc


def _exchange(channel, frame, deadline):
    raw = _encode(frame)
    try:
        while True:
            _wait(channel,deadline,writing=True)
            try:
                sent = channel.send(raw)
            except BlockingIOError:
                continue
            if sent != len(raw):
                raise SandboxError('incomplete sandbox packet')
            break
        return _decode_action(_receive(channel,deadline),frame['seq'])
    except (OSError, BoundaryError) as exc:
        raise SandboxError('sandbox exchange failed') from exc


def run_sandboxed_episode(seed: int, *, horizon: int = 240,
                          timeout: float = 10.) -> tuple[ScoredStep,...]:
    """Fail-closed native confinement, packet deadline and process cleanup."""
    if (type(seed) is not int or not 0 <= seed < 2**32
            or type(horizon) is not int or not 1 <= horizon <= 240
            or type(timeout) not in (int,float) or not 0 < timeout <= 60
            or not math.isfinite(timeout)):
        raise ValueError('bounded episode and timeout')
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise SandboxError('unsupported sandbox platform')
    ctx = mp.get_context('spawn')
    parent,child = socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    parent.setblocking(False)
    process = ctx.Process(target=_worker,args=(child,),daemon=True)
    sim = _episode(seed,horizon)
    deadline = time.monotonic()+timeout
    started = False
    try:
        process.start(); started=True; child.close()
        if _receive(parent,deadline) != b'{"ready":1}':
            raise SandboxError('sandbox not ready')
        observation = next(sim)
        for seq in range(horizon):
            action = _exchange(parent,{'seq':seq,'discrete':observation.discrete,
                'continuous':list(observation.continuous),'damage':observation.damage},deadline)
            try:
                observation = sim.send(action)
            except StopIteration as stop:
                result = stop.value
                break
        else:
            raise SandboxError('simulator did not terminate')
        if len(result) != horizon:
            raise SandboxError('incomplete episode')
        parent.close(); process.join(max(0.,deadline-time.monotonic()))
        if process.is_alive() or process.exitcode != 0 or time.monotonic()>deadline:
            raise SandboxError('worker failed to exit before deadline')
        return result
    finally:
        sim.close(); parent.close(); child.close()
        if started:
            if process.is_alive():
                process.terminate(); process.join(1.)
            if process.is_alive():
                process.kill(); process.join(1.)
            if process.is_alive():
                raise SandboxError('sandbox cleanup failed')
        process.close()
