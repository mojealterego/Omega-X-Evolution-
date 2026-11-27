import json
import multiprocessing as mp
import time

import pytest

from omega_x_evolution.ontos_process_boundary import (
    run_isolated_episode, _worker, _exchange, _decode_action, BoundaryError,
)
from omega_x_evolution.ontos_observation_policy import run_observation_episode


@pytest.mark.parametrize('seed,horizon', [(0,1),(42,120),(9100,240)])
def test_spawned_process_exact_reference_trace(seed,horizon):
    assert run_isolated_episode(seed,horizon=horizon)==run_observation_episode(seed,horizon=horizon)


def _valid(seq=0):
    return {'seq':seq,'discrete':1,'continuous':[1.,.2,-.8,.4,.9,-.3],'damage':0.}


@pytest.mark.parametrize('raw', [b'{}', b'x'*1025, b'{"seq":0,"seq":0}',
    json.dumps({**_valid(),'regime':0}).encode(), json.dumps(_valid(1)).encode(),
    json.dumps({**_valid(),'discrete':True}).encode(),
    json.dumps({**_valid(),'damage':float('nan')}).encode()])
def test_worker_rejects_malformed_or_privileged_input(raw):
    ctx=mp.get_context('spawn'); parent,child=ctx.Pipe()
    p=ctx.Process(target=_worker,args=(child,)); p.start(); child.close()
    try:
        parent.send_bytes(raw)
        assert parent.poll(5)
        with pytest.raises((EOFError, ConnectionResetError)): parent.recv_bytes(1024)
        p.join(5)
        assert p.exitcode==0
    finally:
        parent.close()
        if p.is_alive(): p.terminate(); p.join(2)
        p.close()


def test_worker_rejects_repeated_sequence():
    ctx=mp.get_context('spawn'); parent,child=ctx.Pipe()
    p=ctx.Process(target=_worker,args=(child,)); p.start(); child.close()
    try:
        assert _exchange(parent,_valid(),time.monotonic()+5) in (0,1,2,3,5)
        with pytest.raises(BoundaryError): _exchange(parent,_valid(),time.monotonic()+5)
    finally:
        parent.close();p.join(5)
        if p.is_alive():p.terminate();p.join(2)
        p.close()


def test_exchange_deadline_with_real_unresponsive_pipe():
    ctx=mp.get_context('spawn'); a,b=ctx.Pipe()
    try:
        with pytest.raises(BoundaryError,match='timeout'):
            _exchange(a,_valid(),time.monotonic()+.02)
    finally:a.close();b.close()


@pytest.mark.parametrize('raw',[b'{}',b'{"seq":0,"action":4}',b'{"seq":1,"action":0}',b'{"seq":0,"action":true}',b'{"seq":0,"action":1,"action":2}'])
def test_response_contract_rejects_harm_and_replay(raw):
    with pytest.raises(BoundaryError): _decode_action(raw,0)


@pytest.mark.parametrize('seed,horizon,timeout', [(True,1,5),(-1,1,5),(0,241,5),(0,1,True),(0,1,0),(0,1,61)])
def test_bounds(seed,horizon,timeout):
    with pytest.raises(ValueError):run_isolated_episode(seed,horizon=horizon,timeout=timeout)
