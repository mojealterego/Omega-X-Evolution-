"""Authenticated peer discovery and durable bounded Pareto propagation.

Discovery learns addresses, not trust. Only pre-authorized public keys and
operator-approved IPv4 CIDRs/ports can be used; never scan the public internet.
Each peer remains the independent evaluation authority for received programs.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
import http.client
import ipaddress
import json
from pathlib import Path
import secrets
import ssl
import time
from .checkpoint import CheckpointStore
from .federation import Peer, packet, exchange, verify, digest, _pub, _qualified, MAX_PACKET
from .graph_memory import canonical
from .infrastructure import _lock

MAX_ADS=33
MAX_WIRE=65536
MAX_SEND=128
TTL=300


@dataclass(frozen=True)
class Endpoint:
    public: str
    host: str
    port: int
    def __post_init__(self):
        _pub(self.public)
        ip=ipaddress.ip_address(self.host)
        if ip.version!=4 or ip.is_multicast or ip.is_unspecified or ip.is_link_local or ip.is_reserved or str(ip)!=self.host or type(self.port) is not int or not 1<=self.port<=65535:raise ValueError('endpoint')


class Mesh:
    def __init__(self,path,key,peer,*,networks,ports,create=False,clock=time.time):
        if not isinstance(peer,Peer) or type(networks) is not tuple or not 1<=len(networks)<=16 or type(ports) is not tuple or len(ports)!=2 or any(type(p) is not int for p in ports) or not 1<=ports[0]<=ports[1]<=65535:raise ValueError('mesh policy')
        self.nets=tuple(ipaddress.ip_network(n,strict=True) for n in networks)
        if any(n.version!=4 or n.prefixlen<8 or n.overlaps(ipaddress.ip_network('169.254.0.0/16')) or n.overlaps(ipaddress.ip_network('0.0.0.0/8')) or n.overlaps(ipaddress.ip_network('224.0.0.0/3')) for n in self.nets):raise ValueError('unsafe discovery network')
        self.ports=ports;self.peer=peer;self.path=Path(path).absolute();self.key=key;self.clock=clock;self.store=CheckpointStore(self.path,key)
        self.config=['omega-mesh-v1',peer.config,[str(n) for n in self.nets],list(ports)]
        if create:self.store.initialize({'config':self.config,'ads':{},'serial':0,'sends':{},'sent':{},'counter':0})
        self._load()

    def _load(self):
        rev,state=self.store.load()
        if state['config']!=self.config:raise ValueError('mesh contract mismatch')
        return rev,state

    def _address(self,e,*,self_ok=False):
        if not isinstance(e,Endpoint) or (e.public not in self.peer.allowed and not (self_ok and e.public==self.peer.identity.public)) or not any(ipaddress.ip_address(e.host) in n for n in self.nets) or not self.ports[0]<=e.port<=self.ports[1]:raise ValueError('endpoint outside authorized mesh')
        return e

    def _ad(self,raw,*,fresh=True):
        if type(raw) is not dict or set(raw)!={'body','signature'}:raise ValueError('advertisement envelope')
        b=raw['body']
        if type(b) is not dict or set(b)!={'schema','endpoint','serial','issued','expires'} or b['schema']!='omega-discovery-v1' or any(type(b[k]) is not int for k in ('serial','issued','expires')) or not 1<=b['serial']<=2**53-1 or b['expires']-b['issued']!=TTL:raise ValueError('advertisement body')
        e=self._address(Endpoint(**b['endpoint']),self_ok=True);verify(e.public,b,raw['signature'])
        now=int(self.clock())
        if fresh and (not b['issued']<=now+30 or b['expires']<=now):raise ValueError('expired/future advertisement')
        return e

    def announce(self,e):
        self._address(e,self_ok=True)
        if e.public!=self.peer.identity.public:raise ValueError('own endpoint only')
        with _lock(self.path):
            rev,s=self._load();serial=s['serial']+1;now=int(self.clock());b={'schema':'omega-discovery-v1','endpoint':asdict(e),'serial':serial,'issued':now,'expires':now+TTL}
            raw={'body':b,'signature':self.peer.identity.sign(b)};self._ad(raw)
            s['serial']=serial;s['ads'][e.public]=raw;self.store.save(rev+1,s);return raw

    def endpoints(self):
        _,s=self._load();out={}
        for k,raw in s['ads'].items():
            e=self._ad(raw,fresh=False)
            if e.public!=k:raise ValueError('misbound advertisement')
            if raw['body']['expires']>int(self.clock()) and raw['body']['issued']<=int(self.clock())+30:out[k]=e
        return out

    def answer(self,raw):
        if type(raw) is not dict or set(raw)!={'body','signature'}:raise ValueError('discovery request')
        b=raw['body']
        if type(b) is not dict or set(b)!={'sender','recipient','nonce','schema'} or b['schema']!='omega-discover-request-v1' or b['sender'] not in self.peer.allowed or b['recipient']!=self.peer.identity.public or type(b['nonce']) is not str or len(b['nonce'])!=64:raise ValueError('unauthorized discovery')
        verify(b['sender'],b,raw['signature']);rev,s=self._load();now=int(self.clock());ads=[]
        for ad in s['ads'].values():
            self._ad(ad,fresh=False)
            if ad['body']['expires']>now and ad['body']['issued']<=now+30:ads.append(ad)
        reply={'schema':'omega-discover-reply-v1','sender':self.peer.identity.public,'recipient':b['sender'],'nonce':b['nonce'],'ads':ads}
        return {'body':reply,'signature':self.peer.identity.sign(reply)}

    def discover(self,endpoint,*,tls=None):
        self._address(endpoint);_transport(endpoint.host,tls,server=False)
        b={'schema':'omega-discover-request-v1','sender':self.peer.identity.public,'recipient':endpoint.public,'nonce':secrets.token_hex(32)}
        req={'body':b,'signature':self.peer.identity.sign(b)}
        response=_post(endpoint,'/v1/discover',req,tls=tls)
        if type(response) is not dict or set(response)!={'body','signature'}:raise ValueError('response envelope')
        r=response['body']
        if type(r) is not dict or set(r)!={'schema','sender','recipient','nonce','ads'} or r['schema']!='omega-discover-reply-v1' or r['sender']!=endpoint.public or r['recipient']!=self.peer.identity.public or r['nonce']!=b['nonce'] or type(r['ads']) is not list or len(r['ads'])>MAX_ADS:raise ValueError('discovery response binding')
        verify(endpoint.public,r,response['signature']);learned={}
        for ad in r['ads']:
            # Other trusted peer sets can differ; reject all unknown identities
            # individually without following their endpoint claims.
            try:e=self._ad(ad)
            except (ValueError,TypeError,KeyError):continue
            if e.public==self.peer.identity.public:continue
            previous=learned.get(e.public)
            if previous is not None:raise ValueError('duplicate discovery identity')
            learned[e.public]=ad
        if endpoint.public not in learned or Endpoint(**learned[endpoint.public]['body']['endpoint'])!=endpoint:raise ValueError('discovered endpoint not proven by target')
        with _lock(self.path):
            rev,s=self._load()
            for k,ad in learned.items():
                old=s['ads'].get(k)
                if old and ad['body']['serial']==old['body']['serial'] and ad!=old:raise ValueError('conflicting advertisement')
                if not old or ad['body']['serial']>old['body']['serial']:s['ads'][k]=ad
            self.store.save(rev+1,s)
        return self.endpoints()

    def sync_once(self, bootstrap=(), *, max_contacts=16, tls=None):
        """Bounded authorized discovery/gossip sweep; independently retry on a later tick."""
        if type(bootstrap) is not tuple or len(bootstrap)>MAX_ADS or type(max_contacts) is not int or not 1<=max_contacts<=MAX_ADS:
            raise ValueError('gossip contact budget')
        pending={e.public:e for e in bootstrap if self._address(e)}
        me=self.peer.identity.public
        for k,e in self.endpoints().items():
            if k!=me:pending.setdefault(k,e)
        contacted=set();failed=[];receipts=[]
        while pending and len(contacted)<max_contacts:
            who=min(pending);endpoint=pending.pop(who)
            if who in contacted:continue
            contacted.add(who)
            try:
                known=self.discover(endpoint,tls=tls)
                for k,e in known.items():
                    if k!=me and k not in contacted:pending.setdefault(k,e)
                receipt=self.propagate(who,tls=tls)
                if receipt is not None:receipts.append({'peer':who,'receipt':receipt})
            except (OSError,ValueError,RuntimeError,http.client.HTTPException):failed.append(who)
        return {'contacted':len(contacted),'failed':failed,'receipts':receipts,
                'remaining':len(pending),'known':len(self.endpoints())}

    def propagate(self,recipient,*,codes=None,tls=None):
        if recipient not in self.peer.allowed:raise ValueError('recipient not authorized')
        endpoint=self.endpoints().get(recipient)
        if endpoint is None:raise ValueError('recipient not discovered')
        _transport(endpoint.host,tls,server=False)
        with _lock(self.path):
            rev,s=self._load();pending=s['sends'].get(recipient)
            if pending is None:
                if codes is None:
                    archive=self.peer.archive();from .engine import score
                    codes=tuple(a.code for a in sorted((x for cell in archive.cells[0].values() for x in cell),key=lambda z:(-score(z.metrics),z.id)))
                if type(codes) is not tuple or len(codes)>1024 or any(type(c) is not str or not 1<=len(c)<=2048 for c in codes):raise ValueError('propagation bounds')
                seen=set(s['sent'].get(recipient,[]));fresh=tuple(dict.fromkeys(c for c in codes if digest(c) not in seen))[:8]
                if not fresh:return None
                if s['counter']>=MAX_SEND:raise ValueError('mesh send budget')
                for c in fresh:_qualified(c)
                seq=s['counter']+1;pending=packet(self.peer.identity,recipient,seq,fresh);s['counter']=seq;s['sends'][recipient]=pending
                self.store.save(rev+1,s)
            # Reservation is durable before the network call; exact same packet
            # can be replayed after missing receipt or process death.
            result=exchange(endpoint.host,endpoint.port,pending,tls=tls)
            rev,s=self._load()
            if s['sends'].get(recipient)!=pending:raise ValueError('outbox race')
            s['sent'].setdefault(recipient,[]).extend(digest(c) for c in pending['body']['codes']);del s['sends'][recipient];self.store.save(rev+1,s)
            return result


def _transport(host,tls,*,server):
    ip=ipaddress.ip_address(host)
    if not ip.is_loopback and (not isinstance(tls,ssl.SSLContext) or tls.verify_mode!=ssl.CERT_REQUIRED or (not server and not tls.check_hostname)):raise ValueError('verified mTLS required')


def _post(endpoint,path,body,*,tls=None):
    payload=canonical(body).encode()
    if len(payload)>MAX_WIRE:raise ValueError('discovery wire cap')
    conn=http.client.HTTPSConnection(endpoint.host,endpoint.port,context=tls,timeout=5) if tls else http.client.HTTPConnection(endpoint.host,endpoint.port,timeout=5)
    try:
        conn.request('POST',path,body=payload,headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read(MAX_WIRE+1)
        if r.status!=200 or len(data)>MAX_WIRE:raise ValueError('discovery rejected')
        return json.loads(data)
    finally:conn.close()


def serve(mesh,host='127.0.0.1',port=0,*,tls=None):
    _transport(host,tls,server=True)
    if not isinstance(mesh,Mesh):raise ValueError('mesh required')
    class Handler(BaseHTTPRequestHandler):
        def setup(self):self.request.settimeout(5);super().setup()
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('framing')
                n=int(self.headers['Content-Length']);
                if not 1<=n<=MAX_WIRE:raise ValueError('wire cap')
                data=self.rfile.read(n)
                if len(data)!=n:raise ValueError('truncated request')
                if self.path=='/v1/discover':reply=mesh.answer(json.loads(data))
                elif self.path=='/v1/exchange':reply=mesh.peer.receive(json.loads(data))
                else:raise ValueError('unknown operation')
                out=canonical(reply).encode();status=200
                if len(out)>MAX_WIRE:raise ValueError('wire cap')
            except (ValueError,TypeError,KeyError,RuntimeError,OSError,RecursionError):out=b'{"error":"mesh rejected request"}';status=400
            self.send_response(status);self.send_header('Content-Length',str(len(out)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(out)
    class Server(HTTPServer):
        def get_request(self):
            sock,addr=super().get_request();sock.settimeout(5)
            if tls:
                try:sock=tls.wrap_socket(sock,server_side=True)
                except BaseException:sock.close();raise
            return sock,addr
    return Server((host,port),Handler)
