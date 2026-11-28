from concurrent.futures import ThreadPoolExecutor
import multiprocessing
import os
import shutil
import sqlite3
import pytest
from omega_x_evolution.apex_shield import Limits, MTJ
from omega_x_evolution.apex_twin import Parameters
from omega_x_evolution.apex_planner import Scenario, Event, Plan, evaluate
from omega_x_evolution.ontos_epoch_journal_core import IntegrityError
from omega_x_evolution.apex_campaign import Campaign

S = Scenario(Limits(100, 43000, 1024, 600000, 650000, 1000), Parameters(42850, 10, 100, 3, 2, 64))
W = (MTJ('read', 100), MTJ('read', 100))
P = Plan('safe', (Event(0, W[0]), Event(20, W[1])))
RID = bytes(range(32))


def create(tmp_path, *, scenario=S, plan=P, tenant='tenant-a', run_id=RID, pin=None):
    d = tmp_path / 'private'
    d.mkdir(mode=0o700, exist_ok=True)
    if pin is None:
        pin = Campaign.pin_for(tenant, run_id, W, plan, scenario, 30)
    return Campaign(d/'campaign.db', tenant, run_id, W, plan, scenario, 30, pin)


def test_resume_and_exact_replay(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    one = c.step(start)
    assert one.status == 'COMMITTED'
    c = create(tmp_path)
    assert c.read(one.cursor).index == 1
    two = c.step(one.cursor)
    assert c.read(two.cursor).snapshot == evaluate(W, P, S, 30).final
    assert c.step(two.cursor).status == 'COMPLETE'
    with pytest.raises(IntegrityError):
        c.read(start)


def test_stale_writer_and_explicit_recovery(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    one = c.step(start)
    assert c.step(start).status == 'STALE'
    assert c.recover(start) == one.cursor


def test_concurrent_cas(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    with ThreadPoolExecutor(4) as p:
        results = list(p.map(lambda _: c.step(start), range(8)))
    assert sum(x.status == 'COMMITTED' for x in results) == 1
    assert sum(x.status == 'STALE' for x in results) == 7


def test_rollback_and_tamper(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    backup = tmp_path/'backup'
    shutil.copy2(c.path, backup)
    one = c.step(start)
    shutil.copy2(backup, c.path)
    with pytest.raises(IntegrityError):
        c.read(one.cursor)
    one = c.step(start)
    with sqlite3.connect(c.path) as db:
        db.execute('UPDATE events SET payload=?', (b'bad',))
    with pytest.raises(IntegrityError):
        c.read(one.cursor)


def test_pin_scope_and_unsafe_plan(tmp_path):
    c = create(tmp_path)
    c.provision()
    with pytest.raises(ValueError):
        create(tmp_path, tenant='tenant-b', pin=c.pin)


def test_reject_unsafe_and_cross_run(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    with pytest.raises(IntegrityError):
        create(tmp_path, run_id=b'x'*32).read(start)
    with pytest.raises(ValueError):
        create(tmp_path, plan=Plan('bad', (Event(0, W[0]), Event(1, W[1]))))


def child_commit(c, start):
    if c.step(start).status != 'COMMITTED':
        os._exit(18)
    os._exit(17)


def test_child_exit_after_commit_recovery(tmp_path):
    c = create(tmp_path)
    start = c.provision()
    p = multiprocessing.get_context('spawn').Process(target=child_commit, args=(c, start))
    p.start(); p.join(10)
    if p.is_alive():
        p.kill(); p.join(); pytest.fail('child timeout')
    assert p.exitcode == 17
    latest = c.recover(start)
    assert c.read(latest).index == 1
