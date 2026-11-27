import os
import time

import pytest

from omega_x_evolution.ontos_exec_boundary import (
    Identity, TenantRegistry, run_exec_episode, _launch, _stop,
)
from omega_x_evolution.ontos_sandbox import SandboxError, _receive
from omega_x_evolution.ontos_observation_policy import run_observation_episode


def registry():
    return TenantRegistry((Identity('alpha',61001,61001),Identity('beta',61002,61002)))


@pytest.mark.parametrize('values', [('bad space',61001,61001),('a',0,61001),('a',61001,0),('a',True,61001),('a',65534,61001)])
def test_invalid_identity(values):
    with pytest.raises(ValueError): Identity(*values)


@pytest.mark.parametrize('other',[Identity('alpha',61002,61002),Identity('beta',61001,61002),Identity('beta',61002,61001)])
def test_registry_rejects_aliases(other):
    with pytest.raises(ValueError): TenantRegistry((Identity('alpha',61001,61001),other))


def test_unknown_tenant():
    with pytest.raises(SandboxError): registry().resolve('unknown')


@pytest.mark.skipif(os.geteuid()!=0,reason='native identity switching requires root')
def test_distinct_native_uids_and_secret_fd(monkeypatch,tmp_path):
    monkeypatch.setenv('OMEGA_TEST_SECRET','synthetic-secret-never-in-worker')
    secret=tmp_path/'secret';secret.write_bytes(b'synthetic')
    fd=os.open(secret,os.O_RDONLY);os.set_inheritable(fd,True)
    children=[]
    try:
        for identity in registry().identities:
            channel,p=_launch(identity)
            children.append((channel,p))
            assert _receive(channel,time.monotonic()+10)==b'{"ready":1}'
            with open(f'/proc/{p.pid}/status') as f:
                status=dict(line.split(':',1) for line in f if ':' in line)
            assert status['Uid'].split()==[str(identity.uid)]*4
            assert status['Gid'].split()==[str(identity.gid)]*4
            assert not status['Groups'].strip()
            assert status['NoNewPrivs'].strip()=='1'
        assert children[0][1].pid!=children[1][1].pid
    finally:
        for channel,p in children: _stop(channel,p)
        os.close(fd)


@pytest.mark.skipif(os.geteuid()!=0,reason='native identity switching requires root')
@pytest.mark.parametrize('tenant,seed,horizon',[('alpha',42,120),('beta',9100,240)])
def test_trace(tenant,seed,horizon):
    assert run_exec_episode(registry(),tenant,seed,horizon=horizon)==run_observation_episode(seed,horizon=horizon)


def test_reject_invalid_timeout():
    with pytest.raises(ValueError): run_exec_episode(registry(),'alpha',1,timeout=0)
