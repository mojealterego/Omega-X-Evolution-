"""Bounded certified round changes with autonomous polling and catch-up.

Partial synchrony: progress needs a durable honest quorum, a reachable honest
leader and a sufficiently long common round before the configured limits.
Transport authentication is mandatory for non-local deployments.
"""
from __future__ import annotations
import math
import time
from concurrent.futures import ThreadPoolExecutor
from .bft import Replica, MAX_ROUND, MAX_HEIGHT, leader, make_block, quorum, recover_ops, timeout_quorum, _header, _vote_body, _valid
from .bft_transport import _dispatch, _rpc
from .federation import digest,verify
from .mesh import Endpoint,_transport
import ipaddress
import http.client

_ERRORS=(OSError,ValueError,KeyError,TypeError,IndexError,RuntimeError,http.client.HTTPException)


class Pacemaker:
    def __init__(self,replica,call,*,clock=time.monotonic,base_timeout=30.,max_timeout=300.):
        if not isinstance(replica,Replica) or not callable(call) or not callable(clock) or not all(type(x) in (int,float) and math.isfinite(x) for x in (base_timeout,max_timeout)) or not .01<=base_timeout<=max_timeout<=3600:raise ValueError('pacemaker configuration')
        self.replica=replica;self.call=call;self.clock=clock;self.base=base_timeout;self.maximum=max_timeout
        self.marker=None;self.deadline=0.
        self._reset()
    def _reset(self):
        d=self.replica.inspect();marker=(d['state']['height'],d['round'])
        now=self.clock()
        if not math.isfinite(now):raise ValueError('clock')
        if marker!=self.marker:
            self.marker=marker;self.deadline=now+min(self.maximum,self.base*2**d['round'])
        return d
    def _gather(self,peers,op,args):
        me=self.replica.identity.public;out={}
        def invoke(who):
            return _dispatch(self.replica,op,args) if who==me else self.call(who,op,args)
        # Each peer can run its own tick. The transport sets finite I/O timeouts.
        with ThreadPoolExecutor(max_workers=min(16,max(1,len(peers)))) as pool:
            futures={p:pool.submit(invoke,p) for p in peers}
            for p,f in futures.items():
                try:out[p]=f.result()
                except _ERRORS:continue
        return out
    def tick(self,ops=None):
        d=self._reset();s=d['state'];h,r=self.marker;me=self.replica.identity.public
        if h>MAX_HEIGHT:return {'status':'height-limit','height':h,'round':r}
        def report(status):return {'status':status,'height':h,'round':r}
        views=self._gather(tuple(s['eligible']),'view',[h,r])
        for view in views.values():
            try:
                c=view['commit']
                if c is not None and c['block']['header']['height']==h:
                    if self.replica.commit(c['block'],c['prevote'],c['precommit']):
                        self._reset();return report('caught-up')
            except _ERRORS:continue
        if me not in s['members']:return report('observer')
        if r<MAX_ROUND-1:
            # Advanced peers retain the signed certificate; lagging peers can
            # catch up without trusting a remote clock or claimed round index.
            for v in views.values():
                try:
                    cert=v['timeout_certificate']
                    if cert is not None:
                        self.replica.advance_certified(cert);self._reset();return report('advanced')
                except _ERRORS:continue
        expired=self.clock()>=self.deadline or f'{r}:timeout' in d['votes']
        if expired:
            if r>=MAX_ROUND-1:return report('round-limit')
            own=self.replica.timeout_vote();votes={me:own}
            for who,v in views.items():
                try:
                    raw=v['timeout_vote'];b=raw['body']
                    if who in s['members'] and b=={**_header(s),'round':r,'phase':'timeout','voter':who}:
                        verify(who,b,raw['signature']);votes[who]=raw
                except _ERRORS:continue
            try:cert=timeout_quorum(s,list(votes.values()),r);self.replica.advance_certified(cert);self._reset();return report('advanced')
            except ValueError:return report('waiting-timeout-quorum')
        if me!=leader(s,r):return report('waiting-leader')
        status=self._gather(tuple(s['members']),'status',[]);usable={}
        for who,raw in status.items():
            try:
                b=raw['body']
                if b!={**_header(s),'round':r,'voter':who,'valid':b['valid']}:continue
                verify(who,b,raw['signature']);_valid(s,b['valid'],r);usable[who]=raw
            except _ERRORS:continue
        try:
            if len(usable)<len(s['members'])-s['faults']:return report('waiting-status-quorum')
            # Retry the same persisted proposal, never emit a new signed value.
            p=self.replica.inspect()['votes'].get(f'{r}:proposal')
            if p is None:p=self.replica.propose(make_block(s,recover_ops(s,tuple(usable)) if ops is None else ops),list(usable.values()))
            b=p['body']['block'];value=digest(b)
            def collect(phase,args):
                good=[]
                for who,raw in self._gather(tuple(s['members']),phase,args).items():
                    try:
                        if raw['body']!=_vote_body(s,r,phase,value,who):continue
                        verify(who,raw['body'],raw['signature']);good.append(raw)
                    except _ERRORS:continue
                return quorum(s,good,phase=phase)
            pv=collect('prevote',[p]);pc=collect('precommit',[b,pv])
            self.replica.commit(b,pv,pc)
            self._gather(tuple(x for x in s['members'] if x!=me),'commit',[b,pv,pc]);self._reset();return report('committed')
        except _ERRORS:
            return report('waiting-votes')
    def run(self,stop,*,poll=.25,max_ticks=1024):
        if type(max_ticks) is not int or not 1<=max_ticks<=100000 or not .01<=poll<=60 or not callable(getattr(stop,'wait',None)):raise ValueError('driver bounds')
        last=None
        for _ in range(max_ticks):
            if stop.is_set():break
            last=self.tick()
            if last['status'] in ('height-limit','round-limit'):break
            if stop.wait(poll):break
        return last


def network_driver(replica,endpoints,*,networks,ports,tls=None,**options):
    """Use the production signed HTTP(S) RPC; explicit endpoint allowlist."""
    if type(endpoints) is not tuple or len(endpoints)>31 or type(networks) is not tuple or not 1<=len(networks)<=16 or type(ports) is not tuple or len(ports)!=2 or any(type(p) is not int for p in ports) or not 1<=ports[0]<=ports[1]<=65535:raise ValueError('network bounds')
    nets=tuple(ipaddress.ip_network(x,strict=True) for x in networks)
    if any(n.version!=4 or n.prefixlen<8 or any(n.overlaps(ipaddress.ip_network(b)) for b in ('169.254.0.0/16','0.0.0.0/8','224.0.0.0/3')) for n in nets):raise ValueError('unsafe networks')
    peers={}
    for e in endpoints:
        if not isinstance(e,Endpoint) or e.public in peers or e.public==replica.identity.public or e.public not in replica.g.eligible or not ports[0]<=e.port<=ports[1] or not any(ipaddress.ip_address(e.host) in n for n in nets):raise ValueError('unauthorized endpoint')
        _transport(e.host,tls,server=False);peers[e.public]=e
    def call(peer,op,args):
        if peer not in peers:raise OSError('peer unavailable')
        return _rpc(replica,peers[peer],op,args,tls=tls)
    return Pacemaker(replica,call,**options)
