import ctypes
import errno
import multiprocessing as mp
import os
import socket
import time

import pytest

from omega_x_evolution.ontos_sandbox import install_filter, run_sandboxed_episode, SandboxError, _worker, _exchange, _receive
from omega_x_evolution.ontos_observation_policy import run_observation_episode


def probe(channel, path):
    # Load native library before installing the exact production filter.
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_long]
    inherited_fd=os.open(path,os.O_RDONLY)
    install_filter(channel.fileno())
    results = {}
    def denied(name, operation):
        try:
            operation()
        except OSError as exc:
            results[name] = exc.errno == errno.EPERM
        else:
            results[name] = False
    denied('file_read', lambda: os.open(path, os.O_RDONLY))
    denied('file_write', lambda: os.open(path, os.O_WRONLY))
    denied('directory', lambda: os.listdir('/'))
    denied('network', lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    denied('other_fd', lambda: os.read(inherited_fd, 1))
    denied('signal', lambda: os.kill(os.getpid(), 0))
    child=libc.syscall(57)  # x86_64 fork syscall, bypass Python at-fork hooks
    if child==0: os._exit(1)
    results['fork']=child==-1 and ctypes.get_errno()==errno.EPERM
    denied('exec', lambda: os.execve('/nonexistent', ['nonexistent'], {}))
    denied('chmod', lambda: os.chmod(path, 0o600))
    denied('dup', lambda: os.dup(channel.fileno()))
    denied('new_socketpair', socket.socketpair)
    # PROT_EXEC with MAP_PRIVATE|MAP_ANONYMOUS is denied as well.
    p = libc.mmap(None,4096,4,0x22,-1,0)
    results['executable_mapping'] = p == ctypes.c_void_p(-1).value and ctypes.get_errno() == errno.EPERM
    # PR_GET_NO_NEW_PRIVS itself is blocked after filter installation.
    channel.send(str(results).encode())
    channel.close()


def test_native_denials(tmp_path):
    import ast
    path=tmp_path/'secret'; path.write_text('safe')
    ctx=mp.get_context('spawn')
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    p=ctx.Process(target=probe,args=(b,str(path))); p.start();b.close()
    try:
        a.settimeout(5); result=ast.literal_eval(a.recv(1024).decode())
        assert len(result)==12 and all(result.values()), result
        p.join(5); assert p.exitcode==0
        assert path.read_text()=='safe'
    finally:
        a.close()
        if p.is_alive():p.kill();p.join()
        p.close()


@pytest.mark.parametrize('seed,horizon',[(0,1),(42,120),(9100,240)])
def test_sandbox_reference_trace(seed,horizon):
    assert run_sandboxed_episode(seed,horizon=horizon)==run_observation_episode(seed,horizon=horizon)


def test_timeout_and_no_children():
    before={p.pid for p in mp.active_children()}
    with pytest.raises(SandboxError):run_sandboxed_episode(1,timeout=1e-9)
    assert {p.pid for p in mp.active_children()}==before


@pytest.mark.parametrize('raw',[b'{}',b'x'*1025,b'{"seq":0,"seq":0}',b'{"seq":0,"discrete":1,"continuous":[1,2,3,4,5,6],"damage":0,"regime":0}'])
def test_sandbox_rejects_bad_frame(raw):
    ctx=mp.get_context('spawn'); a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    p=ctx.Process(target=_worker,args=(b,));p.start();b.close();a.setblocking(False)
    try:
        assert _receive(a,time.monotonic()+5)==b'{"ready":1}'
        a.send(raw)
        with pytest.raises(SandboxError):_receive(a,time.monotonic()+5)
        p.join(5); assert p.exitcode==0
    finally:
        a.close()
        if p.is_alive():p.kill();p.join()
        p.close()


def test_no_response_deadline():
    a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET);a.setblocking(False)
    try:
        with pytest.raises(SandboxError,match='timeout'):_receive(a,time.monotonic()+.02)
    finally:a.close();b.close()


def test_kernel_status_and_root_drop():
    ctx=mp.get_context('spawn'); a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    p=ctx.Process(target=_worker,args=(b,));p.start();b.close();a.setblocking(False)
    try:
        assert _receive(a,time.monotonic()+5)==b'{"ready":1}'
        status=dict(line.split(':',1) for line in open(f'/proc/{p.pid}/status') if ':' in line)
        assert status['NoNewPrivs'].strip()=='1'
        assert status['Seccomp'].strip()=='2'
        assert all(int(status[k],16)==0 for k in ('CapEff','CapPrm','CapInh','CapAmb'))
        limits=open(f'/proc/{p.pid}/limits').read()
        from omega_x_evolution.ontos_sandbox import MAX_ADDRESS_SPACE, MAX_CPU_SECONDS
        for label,limit in (('Max address space',MAX_ADDRESS_SPACE),('Max cpu time',MAX_CPU_SECONDS),('Max core file size',0)):
            row=next(x for x in limits.splitlines() if x.startswith(label))
            assert all(int(x)<=limit for x in row[len(label):].split()[:2])
        assert all(int(u)!=0 for u in status['Uid'].split())
        if os.geteuid()==0: assert status['Uid'].split()==['65534']*4
        a.close();p.join(5);assert p.exitcode==0
    finally:
        a.close()
        if p.is_alive():p.kill();p.join()
        p.close()


def test_unsupported_platform_fails_closed(monkeypatch):
    monkeypatch.setattr('omega_x_evolution.ontos_sandbox.platform.machine',lambda:'unsupported')
    with pytest.raises(SandboxError):run_sandboxed_episode(0,horizon=1)
    with pytest.raises(SandboxError):install_filter(3)


def _threaded_probe(channel):
    import threading
    go=threading.Event()
    def try_open():
        go.wait()
        try: os.open('/etc/passwd',os.O_RDONLY)
        except OSError as exc: channel.send(str(exc.errno).encode())
        else: channel.send(b'unexpected success')
    t=threading.Thread(target=try_open);t.start()
    try:
        install_filter(channel.fileno());go.set();t.join()
    finally:
        channel.close()


def test_filter_synchronizes_existing_threads():
    ctx=mp.get_context('spawn');a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
    p=ctx.Process(target=_threaded_probe,args=(b,));p.start();b.close();a.settimeout(5)
    try:
        assert a.recv(1024)==str(errno.EPERM).encode()
        p.join(5);assert p.exitcode==0
    finally:
        a.close()
        if p.is_alive():p.kill();p.join()
        p.close()
