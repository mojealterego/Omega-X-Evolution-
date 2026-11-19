"""Authenticated BFT peer RPC and bounded, per-round leader driver."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
import http.client
import ipaddress
import json
import secrets
from .bft import Replica, MAX_WIRE, leader, make_block, quorum, recover_ops, _header, _valid, _vote_body
from .federation import verify
from .graph_memory import canonical
from .mesh import Endpoint, _transport


def _dispatch(replica,op,args):
    if op=='status' and args==[]:return replica.status()
    if op=='view' and len(args)==2:return replica.view(*args)
    if op=='prevote' and len(args)==1:return replica.prevote(args[0])
    if op=='precommit' and len(args)==2:return replica.precommit(*args)
    if op=='commit' and len(args)==3:return replica.commit(*args)
    raise ValueError('unknown consensus operation')


def serve(replica,host='127.0.0.1',port=0,*,tls=None):
    if not isinstance(replica,Replica):raise ValueError('replica required')
    _transport(host,tls,server=True)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):self.request.settimeout(5);super().setup()
        def log_message(self,*args):pass
        def do_POST(self):
            try:
                if self.path!='/v1/consensus' or self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:raise ValueError('framing')
                n=int(self.headers['Content-Length'])
                if not 1<=n<=MAX_WIRE:raise ValueError('request cap')
                data=self.rfile.read(n)
                if len(data)!=n:raise ValueError('truncated')
                raw=json.loads(data);b=raw['body']
                if set(raw)!={'body','signature'} or set(b)!={'campaign','sender','recipient','nonce','op','args'} or b['campaign']!=replica.g.id or b['sender'] not in replica.g.eligible or b['recipient']!=replica.identity.public or type(b['nonce']) is not str or len(b['nonce'])!=64 or type(b['args']) is not list:raise ValueError('request binding')
                verify(b['sender'],b,raw['signature']);result=_dispatch(replica,b['op'],b['args'])
                response={'campaign':replica.g.id,'sender':replica.identity.public,'recipient':b['sender'],'nonce':b['nonce'],'result':result}
                out=canonical({'body':response,'signature':replica.identity.sign(response)}).encode();status=200
                if len(out)>MAX_WIRE:raise ValueError('response cap')
            except (ValueError,TypeError,KeyError,IndexError,OSError,RuntimeError,RecursionError):out=b'{"error":"consensus request rejected"}';status=400
            self.send_response(status);self.send_header('Content-Length',str(len(out)));self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(out)
    class Server(HTTPServer):
        def get_request(self):
            sock,addr=super().get_request();sock.settimeout(5)
            if tls:
                try:sock=tls.wrap_socket(sock,server_side=True)
                except BaseException:sock.close();raise
            return sock,addr
    return Server((host,port),Handler)


def _rpc(replica,endpoint,op,args,*,tls):
    _transport(endpoint.host,tls,server=False)
    b={'campaign':replica.g.id,'sender':replica.identity.public,'recipient':endpoint.public,'nonce':secrets.token_hex(32),'op':op,'args':args}
    body=canonical({'body':b,'signature':replica.identity.sign(b)}).encode()
    if len(body)>MAX_WIRE:raise ValueError('RPC cap')
    conn=http.client.HTTPSConnection(endpoint.host,endpoint.port,context=tls,timeout=5) if tls else http.client.HTTPConnection(endpoint.host,endpoint.port,timeout=5)
    try:
        conn.request('POST','/v1/consensus',body=body,headers={'Content-Type':'application/json'});r=conn.getresponse();data=r.read(MAX_WIRE+1)
        if r.status!=200 or len(data)>MAX_WIRE:raise ValueError('consensus RPC rejected')
        raw=json.loads(data);v=raw['body']
        if set(raw)!={'body','signature'} or v!={'campaign':replica.g.id,'sender':endpoint.public,'recipient':replica.identity.public,'nonce':b['nonce'],'result':v['result']}:raise ValueError('RPC response binding')
        verify(endpoint.public,v,raw['signature']);return v['result']
    finally:conn.close()


def run_round(replica,endpoints,ops,*,networks,ports,tls=None):
    """Only the current leader runs this finite round. No central service.
    Timeout/failure returns without promotion; caller locally advances round.
    """
    if not isinstance(replica,Replica) or type(endpoints) is not tuple or len(endpoints)>15 or type(networks) is not tuple or not 1<=len(networks)<=16 or type(ports) is not tuple or len(ports)!=2 or any(type(p) is not int for p in ports) or not 1<=ports[0]<=ports[1]<=65535:raise ValueError('round transport bounds')
    nets=tuple(ipaddress.ip_network(x,strict=True) for x in networks)
    if any(n.version!=4 or n.prefixlen<8 or n.overlaps(ipaddress.ip_network('169.254.0.0/16')) or n.overlaps(ipaddress.ip_network('0.0.0.0/8')) or n.overlaps(ipaddress.ip_network('224.0.0.0/3')) for n in nets):raise ValueError('unsafe peer network')
    d=replica.inspect();s=d['state'];me=replica.identity.public
    if me!=leader(s,d['round']):raise ValueError('only current leader')
    seen={me}
    for e in endpoints:
        if not isinstance(e,Endpoint) or e.public in seen or e.public not in s['members'] or not any(ipaddress.ip_address(e.host) in n for n in nets) or not ports[0]<=e.port<=ports[1]:raise ValueError('unauthorized endpoint')
        _transport(e.host,tls,server=False);seen.add(e.public)
    def gather(op,args):
        results={};errors=[]
        try:results[me]=_dispatch(replica,op,args)
        except ValueError:errors.append(me)
        with ThreadPoolExecutor(max_workers=min(16,max(1,len(endpoints)))) as pool:
            tasks=[(e,pool.submit(_rpc,replica,e,op,args,tls=tls)) for e in endpoints]
            for e,f in tasks:
                try:results[e.public]=f.result()
                except (ValueError,OSError,RuntimeError,KeyError,http.client.HTTPException):errors.append(e.public)
        return results,errors
    report={'height':s['height'],'round':d['round'],'committed':False}
    status,_=gather('status',[])
    usable={}
    for who,raw in status.items():
        try:
            b=raw['body']
            if b!={**_header(s),'round':d['round'],'voter':who,'valid':b['valid']}:continue
            verify(who,b,raw['signature']);_valid(s,b['valid'],d['round']);usable[who]=raw
        except (ValueError,KeyError,TypeError,IndexError):continue
    def valid_votes(rows,phase,value):
        out=[]
        for who,raw in rows.items():
            try:
                b=raw['body']
                if b!=_vote_body(s,d['round'],phase,value,who):continue
                verify(who,b,raw['signature']);out.append(raw)
            except (ValueError,KeyError,TypeError,IndexError):continue
        return out
    try:
        # With no explicit operations, recover pending/expired work automatically.
        chosen_ops=recover_ops(s,tuple(usable)) if ops is None else ops
        p=replica.propose(make_block(s,chosen_ops),list(usable.values()));b=p['body']['block']
        from .federation import digest
        value=digest(b);votes,_=gather('prevote',[p]);pv=quorum(s,valid_votes(votes,'prevote',value),phase='prevote')
        commits,_=gather('precommit',[b,pv]);pc=quorum(s,valid_votes(commits,'precommit',value),phase='precommit')
    except ValueError as e:return {**report,'reason':str(e),'participants':len(status)}
    # Local durable commit is the point of no return; subsequent delivery is
    # reported separately and catchup replays certified log records.
    replica.commit(b,pv,pc);delivered,errors=gather('commit',[b,pv,pc])
    return {**report,'committed':True,'participants':len(pc['votes']),'delivered':len(delivered),'unreachable':errors,'block':b,'prevote':pv,'precommit':pc}
