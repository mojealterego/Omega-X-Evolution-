"""Signed peer negotiation of bounded search shards; independent local execution.
Fixed membership, at most f Byzantine voters, n >= 3f+1. A certificate is
n-f distinct votes for one plan per epoch. Safety, not consensus liveness:
conflicting proposals may stall. A new operator-approved campaign is needed
if a quorum cannot be collected. No automatic external provisioning.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from dataclasses import dataclass,asdict
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler,HTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import random
import re
import sqlite3
import ssl
import sys
from .federation import Identity,verify,digest,packet
from .graph_memory import canonical
from .engine import Audit,Archive,Artifact,BASELINE,Cascade,Expression,Genome,apply_patch,score
from .safety_synthesis import prove
from .annealed import propose,ACTIONS
from .holographic import Memory,trajectory
from .epigenetics import Switchboard,Telemetry

MAX_WIRE=2*1024*1024

def _hex(x):return type(x) is str and re.fullmatch('[0-9a-f]{64}',x) is not None

def _signed(identity,body):return {'body':body,'signature':identity.sign(body)}

def _envelope(raw):
    if type(raw) is not dict or set(raw)!={'body','signature'} or type(raw['body']) is not dict or len(canonical(raw).encode())>MAX_WIRE:raise ValueError('invalid signed envelope')
    return raw['body']

@dataclass(frozen=True)
class Campaign:
    session:str
    members:tuple[str,...]
    faults:int=1
    slots:int=32
    epochs:int=4
    seed:int=42
    def __post_init__(self):
        if (not _hex(self.session) or type(self.members) is not tuple or not 1<=len(self.members)<=32 or
          not all(_hex(x) for x in self.members) or tuple(sorted(set(self.members)))!=self.members or
          any(type(x) is not int for x in (self.faults,self.slots,self.epochs,self.seed)) or
          not 0<=self.faults<=(len(self.members)-1)//3 or not len(self.members)<=self.slots<=256 or
          not 1<=self.epochs<=16 or not 0<=self.seed<2**32):raise ValueError('campaign bounds')
    @property
    def quorum(self):return len(self.members)-self.faults
    @property
    def id(self):
        root=Path(__file__).parent
        contract=[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('swarm.py','epigenetics.py','engine.py','safety_synthesis.py','federation.py','annealed.py','holographic.py')]
        return digest(['omega-swarm-v1',asdict(self),list(sys.version_info[:3]),contract])


def proposal(c,identity,epoch,*,offset=0):
    if not isinstance(identity,Identity) or identity.public not in c.members or type(offset) is not int or not 0<=offset<len(c.members):raise ValueError('proposer/offset')
    body={'schema':'omega-shard-plan-v1','campaign':c.id,'epoch':epoch,'proposer':identity.public,'assignments':[c.members[(i+offset+epoch-1)%len(c.members)] for i in range(c.slots)]}
    raw=_signed(identity,body);_check_plan(c,raw);return raw


def _check_plan(c,raw):
    b=_envelope(raw)
    if set(b)!={'schema','campaign','epoch','proposer','assignments'} or b['schema']!='omega-shard-plan-v1' or b['campaign']!=c.id or b['proposer'] not in c.members or type(b['epoch']) is not int or not 1<=b['epoch']<=c.epochs:raise ValueError('incompatible plan')
    a=b['assignments'];n=len(c.members)
    if type(a) is not list or len(a)!=c.slots or any(x not in c.members for x in a) or any(not c.slots//n<=a.count(x)<=math.ceil(c.slots/n) for x in c.members):raise ValueError('unbalanced or incomplete partition')
    verify(b['proposer'],b,raw['signature']);return b


def _vote_body(c,p,voter):return {'schema':'omega-shard-vote-v1','campaign':c.id,'epoch':p['body']['epoch'],'proposal':digest(p),'voter':voter}


def _check_vote(c,p,vote):
    b=_envelope(vote);v=b.get('voter')
    if v not in c.members or b!=_vote_body(c,p,v):raise ValueError('invalid vote')
    verify(v,b,vote['signature']);return v


class BallotStore:
    """Durable signed one-vote lock, independent database per peer.
    Trust operator to prevent whole-file rollback and multiple copies of key.
    Acknowledgement only after SQLite commit; retransmission returns same vote.
    """
    def __init__(self,path,identity,campaign):
        if not isinstance(identity,Identity) or not isinstance(campaign,Campaign) or identity.public not in campaign.members:raise ValueError('peer membership')
        self.path=Path(path).absolute();self.identity=identity;self.c=campaign
        try:os.close(os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600));new=True
        except FileExistsError:new=False
        with closing(self._connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            if new:
                db.execute('CREATE TABLE votes(epoch INTEGER PRIMARY KEY,plan TEXT NOT NULL,vote TEXT NOT NULL)')
                db.execute('CREATE TABLE manifest(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,sig TEXT NOT NULL)')
                db.execute('CREATE TABLE executions(epoch INTEGER PRIMARY KEY,certificate TEXT NOT NULL,result TEXT NOT NULL)')
                db.execute('CREATE TABLE result_manifest(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL,sig TEXT NOT NULL)')
                self._write(db,[]);self._write_results(db,[])
            self._read(db);self._read_results(db)
    def _connect(self):
        db=sqlite3.connect(self.path.as_uri()+'?mode=rw',uri=True,timeout=5)
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA synchronous=FULL');return db
    def _write(self,db,rows):
        b={'campaign':self.c.id,'voter':self.identity.public,'rows':[digest([p,v]) for _,p,v in rows]}
        db.execute('INSERT OR REPLACE INTO manifest VALUES(1,?,?)',(canonical(b),self.identity.sign(b)))
    def _read(self,db):
        row=db.execute('SELECT body,sig FROM manifest WHERE id=1 AND length(body)<8192').fetchone()
        if not row:raise ValueError('missing vote manifest')
        b=json.loads(row[0]);verify(self.identity.public,b,row[1]);rows=[]
        n,m=db.execute('SELECT count(*),coalesce(max(length(plan)+length(vote)),0) FROM votes').fetchone()
        if n>self.c.epochs or m>MAX_WIRE:raise ValueError('vote store bounds')
        for epoch,p,v in db.execute('SELECT epoch,plan,vote FROM votes ORDER BY epoch'):
            p=json.loads(p);v=json.loads(v)
            if epoch!=_check_plan(self.c,p)['epoch'] or _check_vote(self.c,p,v)!=self.identity.public:raise ValueError('corrupted ballot')
            rows.append((epoch,p,v))
        if b!={'campaign':self.c.id,'voter':self.identity.public,'rows':[digest([p,v]) for _,p,v in rows]}:raise ValueError('vote manifest mismatch')
        return rows
    def vote(self,p):
        b=_check_plan(self.c,p);epoch=b['epoch']
        with closing(self._connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');rows=self._read(db)
            for e,old,v in rows:
                if e==epoch:
                    if old!=p:raise ValueError('conflicting proposal: epoch locked')
                    return v
            v=_signed(self.identity,_vote_body(self.c,p,self.identity.public))
            db.execute('INSERT INTO votes VALUES(?,?,?)',(epoch,canonical(p),canonical(v)))
            self._write(db,sorted(rows+[(epoch,p,v)],key=lambda x:x[0]))
        return v
    def _write_results(self,db,rows):
        b={'campaign':self.c.id,'worker':self.identity.public,'rows':[digest([q,r]) for _,q,r in rows]}
        db.execute('INSERT OR REPLACE INTO result_manifest VALUES(1,?,?)',(canonical(b),self.identity.sign(b)))
    def _read_results(self,db):
        row=db.execute('SELECT body,sig FROM result_manifest WHERE id=1 AND length(body)<8192').fetchone()
        if not row:raise ValueError('missing result manifest')
        b=json.loads(row[0]);verify(self.identity.public,b,row[1]);rows=[]
        n,m=db.execute('SELECT count(*),coalesce(max(length(certificate)+length(result)),0) FROM executions').fetchone()
        if n>self.c.epochs or m>2*MAX_WIRE:raise ValueError('execution storage bounds')
        for epoch,q,r in db.execute('SELECT epoch,certificate,result FROM executions ORDER BY epoch'):
            q=json.loads(q);r=json.loads(r);p=verify_certificate(self.c,q);body=_envelope(r)
            if epoch!=p['epoch'] or body.get('worker')!=self.identity.public or body.get('proposal')!=digest(q['proposal']):raise ValueError('corrupt execution')
            verify(self.identity.public,body,r['signature']);rows.append((epoch,q,r))
        if b!={'campaign':self.c.id,'worker':self.identity.public,'rows':[digest([q,r]) for _,q,r in rows]}:raise ValueError('execution manifest mismatch')
        return rows
    def execute(self,q,*,telemetry=None,parents=(),live=False):
        if type(live) is not bool or (live and telemetry is not None):raise ValueError('choose live or supplied telemetry')
        p=verify_certificate(self.c,q);epoch=p['epoch']
        with closing(self._connect()) as db,db:
            db.execute('BEGIN IMMEDIATE');self._read(db);rows=self._read_results(db)
            for e,old,r in rows:
                if e==epoch:
                    if old['proposal']!=q['proposal'] or list(parents)!=r['body']['parents'] or (telemetry is not None and [asdict(t) for t in telemetry]!=r['body']['telemetry']):raise ValueError('execution epoch locked')
                    return r
            r=work(self.c,q,self.identity,telemetry=telemetry,parents=parents,live=live)
            verify_result(self.c,q,r)
            db.execute('INSERT INTO executions VALUES(?,?,?)',(epoch,canonical(q),canonical(r)))
            self._write_results(db,sorted(rows+[(epoch,q,r)],key=lambda x:x[0]))
        return r


def certificate(c,p,votes):
    _check_plan(c,p)
    if type(votes) not in (list,tuple) or not c.quorum<=len(votes)<=len(c.members):raise ValueError('insufficient quorum')
    ids=[_check_vote(c,p,v) for v in votes]
    if len(set(ids))!=len(ids):raise ValueError('duplicate voter')
    return {'proposal':p,'votes':sorted(votes,key=lambda v:v['body']['voter'])}


def verify_certificate(c,q):
    if type(q) is not dict or set(q)!={'proposal','votes'} or q!=certificate(c,q['proposal'],q['votes']):raise ValueError('invalid quorum certificate')
    return q['proposal']['body']


class NeuralRouter:
    """Tiny contextual reward network (6 hidden tanh units), online SGD.
    Deterministic initialization; learned values influence proposals only.
    """
    def __init__(self,seed):
        r=random.Random(seed);self.w=[[r.uniform(-.1,.1) for _ in range(3)] for _ in range(6)];self.v=[[r.uniform(-.1,.1) for _ in range(6)] for _ in range(ACTIONS)]
    def _forward(self,code):
        e=Expression(code);x=(1.,e.count/100,e.operations/100);h=[math.tanh(sum(a*b for a,b in zip(w,x))) for w in self.w];return x,h,[sum(a*b for a,b in zip(v,h)) for v in self.v]
    def choose(self,code,rng):
        _,_,v=self._forward(code)
        return rng.randrange(ACTIONS) if rng.random()<.2 else max(range(ACTIONS),key=lambda i:v[i])
    def update(self,code,action,reward):
        x,h,v=self._forward(code);err=max(-1.,min(1.,v[action]-reward));old=self.v[action][:]
        for j in range(6):
            self.v[action][j]-=.1*err*h[j]
            for k in range(3):self.w[j][k]-=.1*err*old[j]*(1-h[j]**2)*x[k]


def _qualify(code):
    c=prove(code)
    if not c['proved']:return None,c
    r=Cascade(42).evaluate(code)
    return (r.metrics if r.stage==3 and r.metrics[3]==1. else None),c


def _run(c,q,worker,*,telemetry=None,parents=(),live=False):
    """Execute only assigned slots after a valid quorum; no auto-send or remote exec.
    Replay is deterministic for same telemetry/parents. Each local invocation
    is independently budgeted; external operator governs repeated invocation.
    """
    p=verify_certificate(c,q)
    if worker not in c.members:raise ValueError('nonmember')
    slots=[i for i,x in enumerate(p['assignments']) if x==worker]
    if type(live) is not bool or (live and telemetry is not None):raise ValueError('choose live or supplied telemetry')
    if telemetry is None and not live:telemetry=[Telemetry(30,30,30)]*len(slots)
    if not live and (type(telemetry) not in (list,tuple) or len(telemetry)!=len(slots) or not all(isinstance(t,Telemetry) for t in telemetry)):raise ValueError('telemetry must cover assigned slots')
    if type(parents) is not tuple or len(parents)>8 or any(type(x) is not str or not 1<=len(x)<=2048 for x in parents) or len(set(parents))!=len(parents):raise ValueError('seed parent bounds')
    a=Archive(1);initial=[BASELINE]+[x for x in parents if x!=BASELINE]
    for i,code in enumerate(initial):
        m,proof=_qualify(code)
        if m is None:raise ValueError('unqualified input parent')
        a.add(Artifact(f'seed{i}',None,0,0,code,Genome(),m))
    board=Switchboard();router=NeuralRouter(c.seed^p['epoch']);history=[];rows=[];audit=Audit(os.urandom(32),'omega-swarm-v1',Path(__file__).with_name('engine.py'))
    samples=[]
    for j,slot in enumerate(slots):
        t=Telemetry.sample(math.ceil(100*(len(slots)-j)/256)) if live else telemetry[j];samples.append(t)
        mask=board.update(t);enabled=mask['enabled'];rng=random.Random((c.seed<<24)^(p['epoch']<<16)^slot);parent=a.sample(0,rng);action=router.choose(parent.code,rng) if 'neural' in enabled else rng.randrange(ACTIONS)
        code=apply_patch(parent.code,propose(parent.code,action,rng.randrange(2**32)));mode='neural' if 'neural' in enabled else 'uniform';operator=action
        if 'associative' in enabled and history and slot%3==1:
            hit=next((h['record'] for h in Memory(history[-64:]).retrieve(parent.code,3) if h['record']['accepted'] and h['record']['reward']>0),None)
            if hit:code=hit['child'];mode='associative';operator=6
        if 'guided' in enabled and slot%3==2:
            code=f'(({parent.code})-{round(rng.uniform(.1,.9),3)}*abs(x-y))';mode='guided';operator=6
        if len(code)>2048:code=''
        metrics,proof=_qualify(code);ok=metrics is not None;ident=f'slot{slot}';quality=score(metrics) if ok else 0.;base=score(parent.metrics)
        if ok:
            token=audit.issue(ident,code,metrics)
            if not audit.verify(token,ident,code,metrics):raise RuntimeError('audit rejected')
            a.add(Artifact(ident,parent.id,0,p['epoch'],code,Genome(),metrics))
        hist=trajectory(ident,0,parent.id,parent.code,code,operator,ok,quality,base,3 if ok else 0)
        history.append(hist)
        if 'neural' in enabled and operator<ACTIONS:router.update(parent.code,action,hist['reward'])
        rows.append({'slot':slot,'mode':mode,'mask':mask,'code':code,'accepted':ok,'metrics':list(metrics) if ok else None,'proof':proof})
    body={'schema':'omega-shard-result-v1','campaign':c.id,'epoch':p['epoch'],'proposal':digest(q['proposal']),'worker':worker,'telemetry':[asdict(t) for t in samples],'parents':list(parents),'rows':rows}
    return body


def work(c,q,identity,*,telemetry=None,parents=(),live=False):
    if not isinstance(identity,Identity):raise ValueError('identity required')
    return _signed(identity,_run(c,q,identity.public,telemetry=telemetry,parents=parents,live=live))


def verify_result(c,q,raw):
    p=verify_certificate(c,q);b=_envelope(raw);worker=b.get('worker')
    if (set(b)!={'schema','campaign','epoch','proposal','worker','telemetry','parents','rows'} or b['schema']!='omega-shard-result-v1' or b['campaign']!=c.id or b['epoch']!=p['epoch'] or b['proposal']!=digest(q['proposal']) or worker not in c.members):raise ValueError('incompatible result')
    verify(worker,b,raw['signature']);slots=[i for i,x in enumerate(p['assignments']) if x==worker]
    if type(b['rows']) is not list or type(b['telemetry']) is not list or len(b['rows'])!=len(slots) or len(b['telemetry'])!=len(slots) or type(b['parents']) is not list or len(b['parents'])>8:raise ValueError('result budget')
    for code in b['parents']:
        if _qualify(code)[0] is None:raise ValueError('unqualified parent')
    board=Switchboard()
    for slot,t,row in zip(slots,b['telemetry'],b['rows']):
        if type(t) is not dict or set(t)!={'cpu','memory','queue'}:raise ValueError('invalid telemetry')
        mask=board.update(Telemetry(**t))
        if type(row) is not dict or set(row)!={'slot','mode','mask','code','accepted','metrics','proof'} or row['slot']!=slot or row['mask']!=mask or row['mode'] not in ('uniform',*mask['enabled']):raise ValueError('invalid slot or activation')
        m,proof=_qualify(row['code'])
        if row['proof']!=proof or row['accepted'] is not (m is not None) or row['metrics']!=(list(m) if m is not None else None):raise ValueError('independent verification mismatch')
    # Recompute the full deterministic search transcript. Signed telemetry is
    # provenance, not proof that the host actually experienced that load.
    expected=_run(c,q,worker,telemetry=[Telemetry(**t) for t in b['telemetry']],parents=tuple(b['parents']))
    if canonical(b)!=canonical(expected):raise ValueError('search transcript mismatch')
    return b


def aggregate(c,q,results):
    p=verify_certificate(c,q)
    if type(results) not in (tuple,list) or len(results)>len(c.members):raise ValueError('result set bounds')
    bodies=[verify_result(c,q,r) for r in results]
    if len({b['worker'] for b in bodies})!=len(bodies):raise ValueError('duplicate worker report')
    rows=[r for b in bodies for r in b['rows']];accepted=[r for r in rows if r['accepted']]
    return {'epoch':p['epoch'],'planned_slots':c.slots,'executed_slots':len(rows),'missing_slots':sorted(set(range(c.slots))-{r['slot'] for r in rows}),
            'accepted':len(accepted),'champion':max(accepted,key=lambda r:(score(r['metrics']),-r['slot'])) if accepted else None,
            'modes':{m:sum(r['mode']==m for r in rows) for m in ('uniform','neural','associative','guided')}}


def export(c,q,raw,identity,recipient,sequence,limit=4):
    """Bridge independently verified winners into the existing v29 inbox protocol."""
    if type(limit) is not int or not 1<=limit<=8:raise ValueError('export limit')
    b=verify_result(c,q,raw)
    if identity.public!=b['worker']:raise ValueError('worker identity required')
    rows=sorted((r for r in b['rows'] if r['accepted']),key=lambda r:(-score(r['metrics']),r['slot']))
    codes=list(dict.fromkeys(r['code'] for r in rows))[:limit]
    if not codes:raise ValueError('no verified results')
    return packet(identity,recipient,sequence,codes)


def _ip(host):
    ip=ipaddress.ip_address(host)
    if ip.version!=4:raise ValueError('IPv4 literal required')
    return ip


def serve(store,host='127.0.0.1',port=0,*,tls=None):
    if not _ip(host).is_loopback and (not isinstance(tls,ssl.SSLContext) or tls.verify_mode!=ssl.CERT_REQUIRED):raise ValueError('nonloopback requires mTLS')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):self.request.settimeout(5);super().setup()
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                if self.path!='/v1/vote' or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('framing')
                n=int(self.headers['Content-Length'])
                if not 1<=n<=MAX_WIRE:raise ValueError('packet size')
                data=self.rfile.read(n)
                if len(data)!=n:raise ValueError('truncated')
                out=store.vote(json.loads(data));status=200
            except (ValueError,TypeError,KeyError,OSError,sqlite3.Error,RecursionError):out={'error':'vote rejected'};status=400
            data=canonical(out).encode();self.send_response(status);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
    class Server(HTTPServer):
        def get_request(self):
            sock,addr=super().get_request();sock.settimeout(5)
            if tls is not None:
                try:sock=tls.wrap_socket(sock,server_side=True)
                except BaseException:sock.close();raise
            return sock,addr
    return Server((host,port),Handler)


def request_vote(host,port,c,p,peer,*,tls=None):
    _check_plan(c,p)
    if peer not in c.members or type(port) is not int or not 1<=port<=65535:raise ValueError('endpoint')
    if not _ip(host).is_loopback and (not isinstance(tls,ssl.SSLContext) or tls.verify_mode!=ssl.CERT_REQUIRED or not tls.check_hostname):raise ValueError('verified TLS required')
    conn=http.client.HTTPSConnection(host,port,context=tls,timeout=10) if tls else http.client.HTTPConnection(host,port,timeout=10)
    try:
        conn.request('POST','/v1/vote',body=canonical(p).encode(),headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read(8193)
        if r.status!=200 or len(data)>8192:raise ValueError('vote rejected')
        v=json.loads(data)
        if _check_vote(c,p,v)!=peer:raise ValueError('wrong voter')
        return v
    finally:conn.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True);p.add_argument('--db',type=Path)
    sub=p.add_subparsers(dest='action',required=True);b=sub.add_parser('propose');b.add_argument('--epoch',type=int,required=True);b.add_argument('--offset',type=int,default=0)
    b=sub.add_parser('vote');b.add_argument('proposal',type=Path)
    b=sub.add_parser('serve');b.add_argument('--port',type=int,required=True);b.add_argument('--host',default='127.0.0.1');b.add_argument('--ca',type=Path);b.add_argument('--cert',type=Path);b.add_argument('--tls-key',type=Path)
    b=sub.add_parser('request');b.add_argument('proposal',type=Path);b.add_argument('--port',type=int,required=True);b.add_argument('--peer',required=True);b.add_argument('--host',default='127.0.0.1');b.add_argument('--ca',type=Path);b.add_argument('--cert',type=Path);b.add_argument('--tls-key',type=Path)
    b=sub.add_parser('certify');b.add_argument('proposal',type=Path);b.add_argument('votes',nargs='+',type=Path)
    b=sub.add_parser('work');b.add_argument('certificate',type=Path);b.add_argument('--telemetry',type=Path);b.add_argument('--live-telemetry',action='store_true')
    b=sub.add_parser('verify');b.add_argument('certificate',type=Path);b.add_argument('result',type=Path)
    a=p.parse_args()
    def read(path):
        with path.open('rb') as f:data=f.read(MAX_WIRE+1)
        if len(data)>MAX_WIRE:raise ValueError('file cap')
        return json.loads(data)
    data=read(a.campaign);data['members']=tuple(data['members']);c=Campaign(**data)
    with a.key_file.open('rb') as f:identity=Identity(f.read(33))
    def tls(server):
        files=(a.ca,a.cert,a.tls_key)
        if not any(files):return None
        if not all(files):raise ValueError('complete TLS configuration required')
        ctx=ssl.create_default_context(ssl.Purpose.CLIENT_AUTH if server else ssl.Purpose.SERVER_AUTH,cafile=str(a.ca));ctx.verify_mode=ssl.CERT_REQUIRED;ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(str(a.cert),str(a.tls_key));return ctx
    if a.action=='propose':out=proposal(c,identity,a.epoch,offset=a.offset)
    elif a.action=='certify':out=certificate(c,read(a.proposal),[read(x) for x in a.votes])
    elif a.action=='work':
        if a.db is None:p.error('--db required for durable execution')
        out=BallotStore(a.db,identity,c).execute(read(a.certificate),telemetry=[Telemetry(**t) for t in read(a.telemetry)] if a.telemetry else None,live=a.live_telemetry)
    elif a.action=='verify':out=verify_result(c,read(a.certificate),read(a.result))
    elif a.action=='request':out=request_vote(a.host,a.port,c,read(a.proposal),a.peer,tls=tls(False))
    else:
        if a.db is None:p.error('--db required')
        s=BallotStore(a.db,identity,c)
        if a.action=='vote':out=s.vote(read(a.proposal))
        else:
            with serve(s,host=a.host,port=a.port,tls=tls(True)) as server:server.serve_forever()
            return
    print(json.dumps(out,indent=2,allow_nan=False))
if __name__=='__main__':main()
