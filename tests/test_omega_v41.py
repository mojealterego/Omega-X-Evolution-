import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from omega_x_evolution.engine import BASELINE, Cascade, Config, run
from omega_x_evolution.workers import EvaluationInput, evaluate_one
from omega_x_evolution.distributed import Queue, LeaseError, serve, work_once, run_remote


def job():
    c = Cascade(5)
    return EvaluationInput(BASELINE, tuple(c.challenge), c.grid)


def test_lease_recovery_fencing_and_duplicate(tmp_path):
    now = [100.0]
    q = Queue(tmp_path/'q.db', clock=lambda: now[0], lease_seconds=2)
    ident = q.put(job())
    assert q.put(job()) == ident
    a = q.claim('a')
    now[0] += 3
    q = Queue(tmp_path/'q.db', clock=lambda: now[0], lease_seconds=2)
    b = q.claim('b')
    assert b['id'] == a['id'] and b['token'] != a['token']
    output = asdict(evaluate_one(job()))
    with pytest.raises(LeaseError): q.finish('a', a, output)
    q.finish('b', b, output)
    q.finish('b', b, output)
    assert q.result(ident)['result']['stage'] == 3
    assert q.claim('c') is None


def test_renewal_and_owner_binding(tmp_path):
    now = [10.0]
    q = Queue(tmp_path/'q.db', clock=lambda: now[0], lease_seconds=2)
    q.put(job()); a = q.claim('a'); now[0] += 1
    with pytest.raises(LeaseError): q.renew('b', a)
    q.renew('a', a); now[0] += 1.5
    assert q.claim('b') is None
    now[0] += 1
    assert q.claim('b')['token'] != a['token']


def test_remote_worker_protocol_and_auth(tmp_path):
    q = Queue(tmp_path/'q.db'); ident = q.put(job())
    with serve(q, {'a': 'a'*32}) as url:
        with pytest.raises(PermissionError): work_once(url, 'a', 'b'*32)
        assert work_once(url, 'a', 'a'*32)
        assert not work_once(url, 'a', 'a'*32)
    assert q.result(ident)['result']['stage'] == 3


def test_remote_run_matches_local(tmp_path):
    q = Queue(tmp_path/'q.db')
    cfg = Config(seed=5, generations=2, islands=2, workers=2)
    stop = threading.Event()
    with serve(q, {'a':'a'*32, 'b':'b'*32}) as url, ThreadPoolExecutor(2) as pool:
        def worker(name):
            while not stop.is_set():
                if not work_once(url,name,name*32): stop.wait(.01)
        workers = [pool.submit(worker,n) for n in ('a','b')]
        try: assert asyncio.run(run_remote(cfg,q,timeout=10)) == asyncio.run(run(cfg))
        finally: stop.set()
        for w in workers: w.result(timeout=3)


def test_false_result_rejected_by_coordinator(tmp_path):
    q = Queue(tmp_path/'q.db'); ident = q.put(job()); a = q.claim('a')
    output = asdict(evaluate_one(job())); output['result']['metrics'] = [1.,1.,1.,1.]
    q.finish('a', a, output)
    with pytest.raises(LeaseError, match='mismatch'): q.verified(ident,job())


def test_remote_tls_and_fail_closed(tmp_path):
    import ssl, subprocess
    cert, key = tmp_path/'cert.pem', tmp_path/'key.pem'
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1',
        '-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1',
        '-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.load_cert_chain(cert,key)
    q = Queue(tmp_path/'q.db'); q.put(job())
    with pytest.raises(ValueError,match='TLS'):
        with serve(q, {'a':'a'*32},host='0.0.0.0'): pass
    with serve(q,{'a':'a'*32},tls=tls) as url:
        from urllib.error import URLError
        with pytest.raises(URLError): work_once(url,'a','a'*32)
        assert work_once(url,'a','a'*32,context=ssl.create_default_context(cafile=str(cert)))


def test_remote_checkpoint_resume(tmp_path):
    from dataclasses import replace
    from omega_x_evolution.checkpoint import CheckpointStore
    cfg = Config(seed=5,generations=3,islands=2,workers=2)
    store = CheckpointStore(tmp_path/'ck.db',b'k'*32)
    asyncio.run(run(replace(cfg,generations=1),checkpoint=store))
    q = Queue(tmp_path/'q.db'); stop = threading.Event()
    with serve(q,{'a':'a'*32}) as url, ThreadPoolExecutor(1) as pool:
        def worker():
            while not stop.is_set():
                if not work_once(url,'a','a'*32): stop.wait(.01)
        future=pool.submit(worker)
        try: assert asyncio.run(run_remote(cfg,q,checkpoint=store,resume=True,timeout=10)) == asyncio.run(run(cfg))
        finally: stop.set()
        future.result(timeout=3)


def test_retry_exhaustion_and_no_worker_timeout(tmp_path):
    now=[0.]
    q=Queue(tmp_path/'q.db',clock=lambda:now[0],lease_seconds=1,max_attempts=1)
    ident=q.put(job()); q.claim('a'); now[0]=2.
    with pytest.raises(LeaseError,match='exhausted'): q.result(ident)
    assert q.claim('b') is None
    cfg=Config(generations=1,islands=1,workers=1)
    with pytest.raises(TimeoutError): asyncio.run(run_remote(cfg,Queue(tmp_path/'empty.db'),timeout=.1))


def test_worker_keys_must_be_unique(tmp_path):
    q=Queue(tmp_path/'q.db')
    with pytest.raises(ValueError):
        with serve(q,{'a':'a'*32,'b':'a'*32}): pass


def test_concurrent_claims_do_not_share_a_lease(tmp_path):
    q=Queue(tmp_path/'q.db'); q.put(job())
    with ThreadPoolExecutor(8) as pool:
        results=list(pool.map(q.claim, map(str,range(8))))
    assert sum(r is not None for r in results)==1


def test_separate_worker_processes(tmp_path):
    import subprocess, sys
    q=Queue(tmp_path/'q.db'); key=tmp_path/'worker.key'; key.write_text('a'*32)
    c=Cascade(3); jobs=[EvaluationInput(code,tuple(c.challenge),c.grid) for code in ('x+y','-(x+y)','x/0')]
    ids=[q.put(j) for j in jobs]
    with serve(q,{'a':'a'*32}) as url:
        proc=subprocess.run([sys.executable,'-m','omega_x_evolution.distributed','worker','--url',url,'--name','a','--key-file',str(key),'--idle-limit','2'],capture_output=True,timeout=15)
        assert proc.returncode==0,proc.stderr
    import os
    for ident,j in zip(ids,jobs):
        assert q.result(ident)['pid']!=os.getpid()
        assert q.verified(ident,j)==evaluate_one(j)
