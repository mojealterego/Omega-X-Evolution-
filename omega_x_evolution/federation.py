"""Decentralized, authenticated exchange of bounded Pareto fronts.
Every peer owns a private key, durable signed inbox and independently evaluated archive.
No coordinator, auto-discovery, executable remote input or external provisioning.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager, closing
from dataclasses import asdict
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import sqlite3
import ssl
import sys
from .engine import Archive, Artifact, Cascade, Genome, score, apply_patch
from .graph_memory import canonical
from .safety_synthesis import prove
from .quantum import select_elites

MAX_PACKET=65536
MAX_MESSAGES=128
MAX_PEERS=32
SEED=42


def _pub(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):raise ValueError('public key')
    return value


class Identity:
    def __init__(self,key):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        if type(key) is not bytes or len(key)!=32:raise ValueError('Ed25519 private key length')
        self._key=Ed25519PrivateKey.from_private_bytes(key)
        self.public=self._key.public_key().public_bytes_raw().hex()

    def sign(self,body):return self._key.sign(canonical(body).encode()).hex()


def verify(public,body,signature):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    if type(signature) is not str or not re.fullmatch('[a-f0-9]{128}',signature):raise ValueError('signature encoding')
    try:Ed25519PublicKey.from_public_bytes(bytes.fromhex(_pub(public))).verify(bytes.fromhex(signature),canonical(body).encode())
    except InvalidSignature as exc:raise ValueError('signature verification failed') from exc


def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def _contract():
    root=Path(__file__).parent
    return digest(['omega-federation-v1',SEED,list(sys.version_info[:3]),*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('engine.py','safety_synthesis.py','federation.py')]])


def packet(identity,recipient,sequence,codes):
    if (not isinstance(identity,Identity) or type(sequence) is not int or not 1<=sequence<=2**53-1 or
        not isinstance(codes,(tuple,list)) or not 1<=len(codes)<=8 or any(type(c) is not str or not 1<=len(c)<=2048 for c in codes) or len(set(codes))!=len(codes)):
        raise ValueError('packet bounds')
    body={'schema':'omega-federation-v1','contract':_contract(),'sender':identity.public,'recipient':_pub(recipient),'sequence':sequence,'codes':list(codes)}
    return {'body':body,'signature':identity.sign(body)}


def validate(raw,recipient,allowed):
    if type(raw) is not dict or set(raw)!={'body','signature'} or len(canonical(raw).encode())>MAX_PACKET:raise ValueError('packet schema or size')
    b=raw['body']
    if type(b) is not dict or set(b)!={'schema','contract','sender','recipient','sequence','codes'}:raise ValueError('body schema')
    if b['schema']!='omega-federation-v1' or b['contract']!=_contract() or b['recipient']!=recipient or _pub(b['sender']) not in allowed:raise ValueError('untrusted peer or incompatible contract')
    if type(b['sequence']) is not int or not 1<=b['sequence']<=2**53-1 or type(b['codes']) is not list or not 1<=len(b['codes'])<=8 or any(type(c) is not str or not 1<=len(c)<=2048 for c in b['codes']) or len(set(b['codes']))!=len(b['codes']):raise ValueError('invalid payload')
    verify(b['sender'],b,raw['signature'])
    return b


def _qualified(code):
    certificate=prove(code)
    if not certificate['proved']:raise ValueError('unproved candidate')
    result=Cascade(SEED).evaluate(code)
    if result.stage!=3 or result.metrics[3]!=1.:raise ValueError('candidate failed local cascade')
    return result.metrics,certificate


class Peer:
    """One local inbox, signed manifest and monotonic per-sender sequence.
    Imported programs form a separate archive; no injection into live campaigns.
    Whole database rollback/deletion remains an operator backup/trust issue.
    """
    def __init__(self,path,identity,allowed):
        if not isinstance(identity,Identity) or type(allowed) not in (list,tuple,set) or not 1<=len(allowed)<=MAX_PEERS:raise ValueError('peer configuration')
        self.path=Path(path).absolute();self.identity=identity;self.allowed=sorted({_pub(x) for x in allowed})
        if identity.public in self.allowed:raise ValueError('self peer forbidden')
        self.config=['omega-peer-store-v1',_contract(),identity.public,self.allowed]
        try:os.close(os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600));new=True
        except FileExistsError:new=False
        with self._db() as db:
            if new:
                db.execute('CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,sig TEXT NOT NULL)')
                db.execute('CREATE TABLE inbox(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
                self._write_manifest(db,[])
            self._read(db)

    @contextmanager
    def _db(self):
        with closing(sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=5)) as db:
            db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            with db:yield db

    def _write_manifest(self,db,rows):
        body=[self.config,[digest(r) for r in rows]]
        db.execute('INSERT OR REPLACE INTO meta VALUES(1,?,?)',(canonical(body),self.identity.sign(body)))

    def _read(self,db):
        row=db.execute('SELECT body,sig FROM meta WHERE id=1 AND length(body)<=16384').fetchone()
        if not row:raise ValueError('peer manifest missing')
        body=json.loads(row[0]);verify(self.identity.public,body,row[1])
        if type(body) is not list or len(body)!=2 or body[0]!=self.config:raise ValueError('peer configuration mismatch')
        total,maximum=db.execute('SELECT count(*),coalesce(max(length(body)),0) FROM inbox').fetchone()
        if total>MAX_MESSAGES or maximum>MAX_PACKET:raise ValueError('inbox limits')
        rows=[json.loads(r[0]) for r in db.execute('SELECT body FROM inbox ORDER BY id')]
        if body[1]!=[digest(r) for r in rows]:raise ValueError('inbox integrity failure')
        heads={}
        for raw in rows:
            b=validate(raw,self.identity.public,self.allowed)
            if b['sequence']<=heads.get(b['sender'],0):raise ValueError('inbox replay')
            heads[b['sender']]=b['sequence']
        return rows,heads

    def _receipt(self,ident,duplicate,accepted):
        body={'digest':ident,'duplicate':duplicate,'accepted':accepted,'recipient':self.identity.public}
        return {**body,'signature':self.identity.sign(body)}

    def receive(self,raw):
        b=validate(raw,self.identity.public,self.allowed);ident=digest(raw)
        with self._db() as db:
            rows,heads=self._read(db)
            if any(digest(r)==ident for r in rows):return self._receipt(ident,True,0)
            if b['sequence']<=heads.get(b['sender'],0):raise ValueError('stale or conflicting sequence')
            if len(rows)>=MAX_MESSAGES:raise ValueError('inbox capacity reached')
            # All-or-nothing. Sender metrics/claims are not trusted or accepted.
            for code in b['codes']:_qualified(code)
            db.execute('INSERT INTO inbox VALUES(?,?)',(len(rows)+1,canonical(raw)))
            self._write_manifest(db,rows+[raw])
        return self._receipt(ident,False,len(b['codes']))

    def archive(self):
        with self._db() as db:rows,_=self._read(db)
        a=Archive(1)
        for raw in rows:
            b=raw['body']
            for code in b['codes']:
                metrics,_=_qualified(code);ident=digest([b['sender'],b['sequence'],code]);a.add(Artifact(ident,None,0,0,code,Genome(),metrics))
        return a

    def publish(self,memory):
        """Publish authenticated provenance into a local GraphMemory namespace. Idempotent."""
        from .graph_memory import GraphMemory
        if not isinstance(memory,GraphMemory):raise ValueError('graph memory required')
        with self._db() as db:rows,_=self._read(db)
        ids=[]
        for raw in rows:
            b=raw['body'];origin=memory.add('experiment','federated discovery from '+b['sender'],{'packet_sha256':digest(raw),'sender':b['sender'],'sequence':b['sequence'],'recipient':b['recipient']})
            for code in b['codes']:
                metrics,proof=_qualified(code)
                node=memory.add('artifact','verified scheduler expression '+code,{'code':code,'metrics':list(metrics),'certificate':proof})
                memory.link(origin,'produced',node);ids.append(node)
        return sorted(set(ids))

    def export(self,recipient,sequence,*,limit=8):
        a=self.archive();front=[x for cell in a.cells[0].values() for x in cell]
        chosen,report=select_elites(front,limit,seed=sequence%(2**32))
        return packet(self.identity,recipient,sequence,[x.code for x in chosen]),report

    def evolve(self,recipient,sequence,*,budget=32,limit=8,seed=42):
        """Use verified received elites as actual starting points for local bounded mutation."""
        from .annealed import propose
        import random
        if type(budget) is not int or not 1<=budget<=256 or type(seed) is not int or not 0<=seed<2**32:raise ValueError('evolution budget')
        a=self.archive()
        if not a.lineage:raise ValueError('empty federation archive')
        baseline=a.best();rng=random.Random(seed);accepted=0
        for i in range(budget):
            parent=a.sample(0,rng);weight=round(rng.uniform(.1,.9),3)
            if i%2==0:code=f'(({parent.code})-{weight}*abs(x-y))'
            else:code=apply_patch(parent.code,propose(parent.code,rng.randrange(6),rng.randrange(2**32)))
            try:metrics,_=_qualified(code)
            except ValueError:continue
            ident=digest(['local',self.identity.public,sequence,seed,i,code]);a.add(Artifact(ident,parent.id,0,1,code,Genome(),metrics));accepted+=1
        chosen,r=select_elites([x for cell in a.cells[0].values() for x in cell],limit,seed=seed)
        return packet(self.identity,recipient,sequence,[x.code for x in chosen]),{'attempts':budget,'accepted':accepted,'baseline':score(baseline.metrics),'champion':score(a.best().metrics),'selection':r}


def export_store(store,identity,recipient,sequence,*,limit=8,sampler=None,authorized=False,reads=64):
    """Export from an authenticated completed/running cluster checkpoint, never mutate it."""
    from .cluster import Store, restore_archive
    if not isinstance(store,Store):raise ValueError('authenticated cluster store required')
    store.open();front=[]
    for i in range(store.cfg.islands):
        _,state=store.read(i);a=restore_archive(state,store.cfg)
        for cell in a.cells[0].values():
            for x in cell:
                front.append(x)
    unique={}
    for x in sorted(front,key=lambda a:(-score(a.metrics),a.id)):unique.setdefault(x.code,x)
    qualified=[]
    for x in list(unique.values())[:64]:
        try:metrics,_=_qualified(x.code)
        except ValueError:continue
        qualified.append(Artifact(x.id,None,0,0,x.code,Genome(),metrics))
    chosen,r=select_elites(qualified,limit,seed=sequence%(2**32),sampler=sampler,authorized=authorized,reads=reads)
    return packet(identity,recipient,sequence,[x.code for x in chosen]),r


def _ip(host):
    ip=ipaddress.ip_address(host)
    if ip.version!=4:raise ValueError('IPv4 literal required')
    return ip


def serve(peer,host='127.0.0.1',port=0,*,tls=None):
    if not _ip(host).is_loopback and (not isinstance(tls,ssl.SSLContext) or tls.verify_mode != ssl.CERT_REQUIRED):raise ValueError('non-loopback requires mutual TLS')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.request.settimeout(5);super().setup()
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                if self.path!='/v1/exchange' or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('request framing')
                n=int(self.headers['Content-Length'])
                if not 1<=n<=MAX_PACKET:raise ValueError('request size')
                payload=self.rfile.read(n)
                if len(payload)!=n:raise ValueError('truncated input')
                res=peer.receive(json.loads(payload));status=200
            except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,RecursionError):res={'error':'exchange rejected'};status=400
            out=canonical(res).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(out)));self.end_headers();self.wfile.write(out)
    class Server(HTTPServer):
        def get_request(self):
            sock,addr=super().get_request();sock.settimeout(5)
            if tls is not None:
                try:sock=tls.wrap_socket(sock,server_side=True)
                except BaseException:sock.close();raise
            return sock,addr
    return Server((host,port),Handler)


def exchange(host,port,raw,*,tls=None):
    if not _ip(host).is_loopback and (not isinstance(tls,ssl.SSLContext) or tls.verify_mode!=ssl.CERT_REQUIRED or not tls.check_hostname):raise ValueError('non-loopback requires verified TLS')
    if type(port) is not int or not 1<=port<=65535:raise ValueError('port')
    body=canonical(raw).encode()
    if len(body)>MAX_PACKET:raise ValueError('packet budget')
    conn=http.client.HTTPSConnection(host,port,context=tls,timeout=10) if tls else http.client.HTTPConnection(host,port,timeout=10)
    try:
        conn.request('POST','/v1/exchange',body=body,headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read(4097)
        if r.status!=200 or len(data)>4096:raise ValueError('peer rejected exchange')
        res=json.loads(data)
        if type(res) is not dict or set(res)!={'digest','duplicate','accepted','recipient','signature'} or res['recipient']!=raw['body']['recipient']:raise ValueError('invalid receipt identity')
        verify(res['recipient'],{k:v for k,v in res.items() if k!='signature'},res['signature'])
        if res.get('digest')!=digest(raw) or type(res.get('duplicate')) is not bool or res.get('accepted')!=(0 if res['duplicate'] else len(raw['body']['codes'])):raise ValueError('invalid peer receipt')
        return res
    finally:conn.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--key-file',type=Path,required=True);p.add_argument('--db',type=Path);p.add_argument('--allow',action='append',default=[])
    sub=p.add_subparsers(dest='action',required=True);sub.add_parser('public');sub.add_parser('inspect')
    b=sub.add_parser('pack');b.add_argument('--recipient',required=True);b.add_argument('--sequence',type=int,required=True);b.add_argument('codes',nargs='+')
    b=sub.add_parser('export');b.add_argument('--recipient',required=True);b.add_argument('--sequence',type=int,required=True);b.add_argument('--evolve',type=int,default=0)
    b=sub.add_parser('receive');b.add_argument('packet',type=Path)
    b=sub.add_parser('serve');b.add_argument('--port',type=int,required=True);b.add_argument('--host',default='127.0.0.1');b.add_argument('--ca',type=Path);b.add_argument('--cert',type=Path);b.add_argument('--tls-key',type=Path)
    b=sub.add_parser('send');b.add_argument('--port',type=int,required=True);b.add_argument('--host',default='127.0.0.1');b.add_argument('--ca',type=Path);b.add_argument('--cert',type=Path);b.add_argument('--tls-key',type=Path);b.add_argument('packet',type=Path)
    a=p.parse_args()
    with a.key_file.open('rb') as f:identity=Identity(f.read(33))
    def read():
        with a.packet.open('rb') as f:raw=f.read(MAX_PACKET+1)
        if len(raw)>MAX_PACKET:raise ValueError('packet cap')
        return json.loads(raw)
    def tls(server):
        files=(a.ca,a.cert,a.tls_key)
        if not any(files):return None
        if not all(files):raise ValueError('CA, certificate, and TLS key all required')
        ctx=ssl.create_default_context(ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH,cafile=str(a.ca));ctx.verify_mode=ssl.CERT_REQUIRED;ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(str(a.cert),str(a.tls_key));return ctx
    if a.action=='public':res={'public':identity.public}
    elif a.action=='pack':res=packet(identity,a.recipient,a.sequence,a.codes)
    elif a.action=='send':res=exchange(a.host,a.port,read(),tls=tls(False))
    else:
        if a.db is None:p.error('--db required')
        peer=Peer(a.db,identity,a.allow)
        if a.action=='receive':res=peer.receive(read())
        elif a.action=='export':res=(peer.evolve(a.recipient,a.sequence,budget=a.evolve) if a.evolve else peer.export(a.recipient,a.sequence))[0]
        elif a.action=='inspect':
            archive=peer.archive();res={'artifacts':len(archive.lineage),'occupied_cells':len(archive.cells[0]),'champion':asdict(archive.best()) if archive.lineage else None}
        else:
            with serve(peer,host=a.host,port=a.port,tls=tls(True)) as server:server.serve_forever()
            return
    print(json.dumps(res,indent=2,allow_nan=False))


if __name__=='__main__':main()
