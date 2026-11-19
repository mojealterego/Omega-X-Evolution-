"""Durable leased evaluation queue and authenticated HTTP worker transport.

The controller independently recomputes every result before promotion. Workers
receive only public evaluation inputs. No pickle or candidate code execution.
"""
from __future__ import annotations

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, closing
from dataclasses import asdict
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import secrets
import sqlite3
import ssl
import threading
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler

from .workers import EvaluationInput, evaluate_one

MAX_BODY = 128 * 1024


class LeaseError(RuntimeError):
    pass


def encode(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    if len(data) > MAX_BODY:
        raise ValueError('message too large')
    return data


def input_job(value):
    if set(value) != {'code', 'challenge', 'grid'}:
        raise ValueError('invalid evaluation input')
    if not isinstance(value['code'], str) or len(value['code']) > 2048:
        raise ValueError('invalid candidate')
    def points(items):
        if not isinstance(items, (list, tuple)) or not 1 <= len(items) <= 256:
            raise ValueError('point budget')
        if any(not isinstance(p, (list, tuple)) or len(p) != 2 or any(type(x) not in (int,float) or not 0 <= x <= 1 for x in p) for p in items):
            raise ValueError('invalid point')
        return tuple(tuple(p) for p in items)
    return EvaluationInput(value['code'], points(value['challenge']), points(value['grid']))


def output_value(value):
    if set(value) != {'result', 'failed_points', 'pid'} or type(value['pid']) is not int or value['pid'] <= 0:
        raise ValueError('invalid result')
    result = value['result']
    if set(result) != {'stage','metrics','reason'} or type(result['stage']) is not int or result['stage'] not in range(4):
        raise ValueError('invalid stage')
    m = result['metrics']
    if len(m) != 4 or any(type(x) not in (int,float) or not 0 <= x <= 1 for x in m):
        raise ValueError('invalid metrics')
    if not isinstance(result['reason'], str) or len(result['reason']) > 2048:
        raise ValueError('invalid reason')
    f = value['failed_points']
    if not isinstance(f,(list,tuple)) or len(f)>256 or any(not isinstance(p,(list,tuple)) or len(p)!=2 or any(type(x) not in (float,int) or not 0<=x<=1 for x in p) for p in f):
        raise ValueError('invalid failure points')
    return encode(value)


class Queue:
    def __init__(self, path, *, lease_seconds=15., max_attempts=4, clock=time.time):
        if not 0 < lease_seconds <= 300 or not 1 <= max_attempts <= 32:
            raise ValueError('invalid lease configuration')
        self.path, self.lease_seconds, self.max_attempts, self.clock = Path(path), lease_seconds, max_attempts, clock
        try: os.close(os.open(self.path, os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
        except FileExistsError: pass
        self.contract = hashlib.sha256(encode(["omega-remote-v1",list(sys.version_info[:3]), *(hashlib.sha256(Path(__file__).with_name(p).read_bytes()).hexdigest() for p in ("engine.py","workers.py","safety_synthesis.py","modal.py","interval_checker.py"))])).digest()
        with self.tx() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload BLOB NOT NULL, owner TEXT, token TEXT, expiry REAL, attempts INTEGER NOT NULL DEFAULT 0, output BLOB)')

    @contextmanager
    def tx(self):
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                db.execute('BEGIN IMMEDIATE')
                yield db

    def put(self, job):
        payload = encode(asdict(input_job(asdict(job))))
        ident = hashlib.sha256(self.contract+payload).hexdigest()
        with self.tx() as db:
            db.execute('INSERT OR IGNORE INTO jobs(id,payload) VALUES (?,?)', (ident,payload))
        return ident

    def claim(self, worker):
        with self.tx() as db:
            now = self.clock()
            row = db.execute('SELECT id,payload FROM jobs WHERE output IS NULL AND attempts<? AND (expiry IS NULL OR expiry<=?) ORDER BY rowid LIMIT 1', (self.max_attempts,now)).fetchone()
            if not row: return None
            token = secrets.token_hex(32)
            db.execute('UPDATE jobs SET owner=?,token=?,expiry=?,attempts=attempts+1 WHERE id=?', (worker,token,now+self.lease_seconds,row[0]))
        return {'id':row[0], 'token':token, 'job':json.loads(row[1])}

    def renew(self, worker, lease):
        with self.tx() as db:
            now = self.clock()
            n = db.execute('UPDATE jobs SET expiry=? WHERE id=? AND owner=? AND token=? AND output IS NULL AND expiry>?', (now+self.lease_seconds,lease['id'],worker,lease['token'],now)).rowcount
            if n != 1: raise LeaseError('stale lease')

    def finish(self, worker, lease, result):
        payload = output_value(result)
        with self.tx() as db:
            row = db.execute('SELECT output,expiry FROM jobs WHERE id=? AND owner=? AND token=?', (lease['id'],worker,lease['token'])).fetchone()
            if row is None: raise LeaseError('stale lease')
            if row[0] is not None:
                if row[0] == payload: return
                raise LeaseError('conflicting completion')
            if row[1] <= self.clock(): raise LeaseError('expired lease')
            db.execute('UPDATE jobs SET output=? WHERE id=?', (payload,lease['id']))

    def result(self, ident):
        with self.tx() as db:
            row = db.execute('SELECT output, attempts, expiry FROM jobs WHERE id=?',(ident,)).fetchone()
        if row is None: raise LeaseError('unknown job')
        if row[0] is not None: return json.loads(row[0])
        if row[1]>=self.max_attempts and row[2]<=self.clock(): raise LeaseError('attempt budget exhausted')
        return None

    def verified(self, ident, job):
        received = self.result(ident)
        if received is None: return None
        expected = evaluate_one(job)
        body = asdict(expected); body['pid'] = received['pid']
        if encode(body) != encode(received): raise LeaseError('remote result mismatch')
        return expected


def loopback(host):
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False


@contextmanager
def serve(queue, keys, host='127.0.0.1', port=0, *, tls=None):
    if not isinstance(keys,dict) or not 1<=len(keys)<=128 or any(not isinstance(k,str) or not 1<=len(k)<=64 or not k.isascii() or not k.isalnum() or not isinstance(v,str) or not 32<=len(v)<=256 or not v.isascii() or not v.isalnum() for k,v in keys.items()) or len(set(keys.values()))!=len(keys):
        raise ValueError('worker key contract: 32–256 ASCII alphanumeric characters')
    if not loopback(host) and tls is None: raise ValueError('TLS required outside loopback')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def setup(self):
            super().setup(); self.connection.settimeout(5)
        def do_POST(self):
            worker = self.headers.get('X-Worker','')
            key = keys.get(worker)
            auth = self.headers.get('Authorization','')
            if key is None or not hmac.compare_digest(auth.encode(), ('Bearer '+key).encode()):
                self.send_error(401); return
            try:
                length = int(self.headers.get('Content-Length','-1'))
                if not 0<=length<=MAX_BODY: raise ValueError('invalid length')
                body = json.loads(self.rfile.read(length))
                if self.path == '/claim': result = queue.claim(worker)
                elif self.path == '/renew': queue.renew(worker,body); result = True
                elif self.path == '/finish': queue.finish(worker,body['lease'],body['output']); result = True
                else: self.send_error(404); return
                data = encode(result)
            except LeaseError: self.send_error(409); return
            except (ValueError,TypeError,KeyError,OverflowError): self.send_error(400); return
            except sqlite3.Error: self.send_error(503); return
            self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    class Server(HTTPServer):
        def get_request(self):
            sock, address = super().get_request()
            sock.settimeout(5)
            if tls is not None:
                try: sock = tls.wrap_socket(sock,server_side=True)
                except OSError:
                    sock.close(); raise
            return sock,address
    server = Server((host,port),Handler)
    try:
        worker = threading.Thread(target=server.serve_forever,daemon=True); worker.start()
        try: yield f'{"https" if tls else "http"}://{host}:{server.server_port}'
        finally: server.shutdown(); worker.join()
    finally: server.server_close()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None


def work_once(url, name, key, *, context=None):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or (parsed.scheme=='http' and not loopback(parsed.hostname)):
        raise ValueError('invalid coordinator endpoint')
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context or ssl.create_default_context()))
    def call(path, body):
        req = Request(url.rstrip('/')+path, data=encode(body), headers={'X-Worker':name,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        try:
            with opener.open(req, timeout=10) as response:
                data = response.read(MAX_BODY+1)
                if len(data)>MAX_BODY: raise ValueError('response too large')
                return json.loads(data)
        except HTTPError as exc:
            if exc.code==401: raise PermissionError('worker rejected') from exc
            if exc.code==409: raise LeaseError('lease lost') from exc
            raise
    lease = call('/claim',{})
    if lease is None: return False
    job = input_job(lease['job'])
    call('/renew',{'id':lease['id'],'token':lease['token']})
    output = asdict(evaluate_one(job))
    call('/finish',{'lease':{'id':lease['id'],'token':lease['token']},'output':output})
    return True


class RemoteExecutor(ThreadPoolExecutor):
    def __init__(self, queue, timeout, workers):
        super().__init__(max_workers=workers); self.queue=queue; self.timeout=timeout
    def submit(self, fn, /, *args, **kwargs):
        if fn is not evaluate_one or len(args)!=1 or kwargs: raise ValueError('unsupported remote task')
        def wait():
            ident = self.queue.put(args[0]); deadline = time.monotonic()+self.timeout
            while time.monotonic()<deadline:
                output = self.queue.verified(ident,args[0])
                if output is not None: return output
                time.sleep(.02)
            raise TimeoutError('remote evaluation deadline')
        return super().submit(wait)


async def run_remote(cfg, queue, *, timeout=60., checkpoint=None, resume=False, performance_policy=None):
    from .engine import _run, simulated_proposal
    if not math.isfinite(timeout) or not 0<timeout<=3600: raise ValueError('invalid timeout')
    with RemoteExecutor(queue,timeout,min(32,cfg.workers*cfg.islands)) as executor:
        return await _run(cfg,simulated_proposal,checkpoint=checkpoint,resume=resume,executor=executor,performance_policy=performance_policy)


def main():
    from .engine import Config
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='mode',required=True)
    s=sub.add_parser('controller'); s.add_argument('--db',required=True); s.add_argument('--keys',required=True,type=Path); s.add_argument('--host',default='127.0.0.1'); s.add_argument('--port',type=int,default=8787); s.add_argument('--cert'); s.add_argument('--tls-key'); s.add_argument('--seed',type=int,default=5); s.add_argument('--generations',type=int,default=5)
    s.add_argument('--performance-regression',action='store_true')
    w=sub.add_parser('worker'); w.add_argument('--url',required=True); w.add_argument('--name',required=True); w.add_argument('--key-file',required=True,type=Path); w.add_argument('--ca'); w.add_argument('--idle-limit',type=int,default=100)
    a=p.parse_args()
    if a.mode=='controller':
        if bool(a.cert)!=bool(a.tls_key): p.error('both certificate and TLS key required')
        tls=None
        if a.cert:
            tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); tls.minimum_version=ssl.TLSVersion.TLSv1_2; tls.load_cert_chain(a.cert,a.tls_key)
        from .performance import Policy
        q=Queue(a.db)
        with serve(q,json.loads(a.keys.read_text()),a.host,a.port,tls=tls):
            print(json.dumps(asyncio.run(run_remote(Config(seed=a.seed,generations=a.generations),q,performance_policy=Policy() if a.performance_regression else None)),allow_nan=False))
    else:
        key=a.key_file.read_text().strip(); ctx=ssl.create_default_context(cafile=a.ca); idle=0
        if not 1<=a.idle_limit<=10000: p.error('invalid idle limit')
        while idle<a.idle_limit:
            try: success=work_once(a.url,a.name,key,context=ctx)
            except PermissionError: raise
            except (OSError,LeaseError): success=False
            if success: idle=0
            else: idle+=1; time.sleep(.1)


if __name__=='__main__': main()
