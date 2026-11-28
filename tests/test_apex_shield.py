from dataclasses import replace
import pytest
from omega_x_evolution.apex_shield import Limits, Telemetry, HTP, FeRAM, ReRAM, MTJ, decide

L=Limits(100,43000,8*1024*1024,600000,650000,1000)
T=Telemetry(100,40000,1024,True,False,True)

@pytest.mark.parametrize('action',[
    HTP(8*1024*1024-1024,0), FeRAM('status','qpi',80,0,0),
    FeRAM('frqad','qpi',80,0,4), FeRAM('write','xip',100,4,4),
    ReRAM('write',256), ReRAM('poll',0), MTJ('write',600000), MTJ('read',200)])
def test_admits_only_bounded_model_actions(action):
    assert decide(L,T,action,now=110).allowed

@pytest.mark.parametrize('action,telemetry',[
    (HTP(8*1024*1024,0),T), (HTP(1,1),T), (HTP(True,0),T),
    (FeRAM('frqad','qpi',80,0,4),replace(T,feram_ready=False)),
    (FeRAM('write','qpi',79,0,4),T), (FeRAM('write','xip',99,0,4),T),
    (FeRAM('write','qpi',80,1,4),T), (FeRAM('write','qpi',80,0,1),T),
    (FeRAM('read','qpi',80,1048575,4),T), (ReRAM('write',257),T),
    (ReRAM('write',256),replace(T,reram_busy=True)),
    (ReRAM('write',256),replace(T,reram_polled=False)),
    (MTJ('write',600001),T), (MTJ('read',201),T), (MTJ('write',True),T),
    (HTP(1,0),replace(T,temp_mc=43000)), (HTP(1,0),replace(T,observed_ms=9)),
    (HTP(1,0),replace(T,observed_ms=111)), (object(),T)])
def test_fail_closed(action,telemetry):
    assert not decide(L,telemetry,action,now=110).allowed


def test_uncalibrated_mtj_and_backhop_boundary():
    assert not decide(replace(L,mtj_write_max_uv=None),T,MTJ('write',100),now=110).allowed
    limits=replace(L,mtj_write_max_uv=700000)
    assert decide(limits,T,MTJ('write',649999),now=110).allowed
    assert not decide(limits,T,MTJ('write',650000),now=110).allowed
    assert not decide(replace(L,mtj_ic0_ua=None),T,MTJ('read',1),now=110).allowed


def test_exhaustive_integer_threshold_neighborhood():
    for current in range(195,206):
        assert decide(L,T,MTJ('read',current),now=110).allowed==(current<=200)
    for gap in range(75,105):
        for mode,minimum in (('qpi',80),('xip',100)):
            assert decide(L,T,FeRAM('read',mode,gap,0,4),now=110).allowed==(gap>=minimum)
    assert not decide(L,T,HTP(1,0),now=True).allowed
