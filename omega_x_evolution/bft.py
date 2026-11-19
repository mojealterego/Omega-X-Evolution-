"""Bounded replicated search ledger with round locks and quorum certificates.

Tendermint-style safety under authenticated static-per-height membership,
<=f Byzantine validators, durable non-equivocation and no disk rollback.
Round timeouts and network transport are caller-controlled; not a production
implementation of Tendermint or an unconditional liveness guarantee.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from .checkpoint import CheckpointStore
from .federation import Identity, verify, digest, _pub, packet
from .graph_memory import canonical
from .infrastructure import _lock
from .engine import Cascade, apply_patch
from .annealed import propose as mutate
from .safety_synthesis import prove

MAX_HEIGHT=128
MAX_ROUND=32
MAX_TASKS=64
MAX_OPS=16
MAX_WIRE=2*1024*1024


def _wire(value):return json.loads(canonical(value))
def _hex(x):return type(x) is str and len(x)==64 and all(c in '0123456789abcdef' for c in x)
def _signed(i,b):return {'body':b,'signature':i.sign(b)}
def _envelope(raw):
    if type(raw) is not dict or set(raw)!={'body','signature'} or type(raw['body']) is not dict or len(canonical(raw).encode())>MAX_WIRE:raise ValueError('BFT envelope')
    return raw['body']


def _membership(m,f):
    if type(m) not in (tuple,list) or not 1<=len(m)<=16 or tuple(m)!=tuple(sorted(set(m))) or any(not _hex(x) for x in m) or type(f) is not int or not 0<=f<=(len(m)-1)//3:raise ValueError('membership bounds')


@dataclass(frozen=True)
class Genesis:
    campaign:str
    members:tuple[str,...]
    eligible:tuple[str,...]
    faults:int
    budget:int
    lease_heights:int=3
    def __post_init__(self):
        _membership(self.members,self.faults)
        if not _hex(self.campaign) or type(self.eligible) is not tuple or len(self.eligible)>32 or tuple(sorted(set(self.eligible)))!=self.eligible or any(not _hex(x) for x in self.eligible) or not set(self.members)<=set(self.eligible) or type(self.budget) is not int or not 1<=self.budget<=256 or type(self.lease_heights) is not int or not 2<=self.lease_heights<=16:raise ValueError('genesis bounds')
    @property
    def id(self):
        root=Path(__file__).parent
        return digest(['omega-bft-v1',asdict(self),*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('bft.py','engine.py','annealed.py','federation.py','safety_synthesis.py','interval_checker.py','modal.py')]])


def initial(g):
    return {'campaign':g.id,'height':1,'parent':g.id,'members':list(g.members),'eligible':list(g.eligible),'faults':g.faults,'budget':g.budget,'lease_heights':g.lease_heights,'spent':0,'tasks':{}}


def leader(s,round):
    if type(round) is not int or not 0<=round<MAX_ROUND:raise ValueError('round bound')
    return s['members'][(s['height']-1+round)%len(s['members'])]


def _header(s):return {'campaign':s['campaign'],'height':s['height'],'parent':s['parent'],'membership':digest([s['members'],s['faults']])}


def _result_body(s,t,identity):
    job=s['tasks'][t]
    if job['worker']!=identity or job['result'] is not None or s['height']>=job['expires']:raise ValueError('task lease not active')
    code=apply_patch(job['parent'],mutate(job['parent'],job['action'],job['seed']))
    result=Cascade(42).evaluate(code)
    return {'campaign':s['campaign'],'task':t,'attempt':job['attempt'],'worker':identity,'code':code,'stage':result.stage,'metrics':list(result.metrics),'certificate':prove(code)}


def task_result(s,t,identity):
    if not isinstance(identity,Identity):raise ValueError('worker identity required')
    return _signed(identity,_result_body(s,t,identity.public))


def _apply(s,b):
    if type(b) is not dict or set(b)!={'header','ops'} or b['header']!=_header(s) or s['height']>MAX_HEIGHT or type(b['ops']) is not list or len(b['ops'])>MAX_OPS or len(canonical(b).encode())>MAX_WIRE:raise ValueError('invalid block')
    out=_wire(s); height=s['height']; changed=set();ops=b['ops']
    for op in ops:
        if type(op) is not dict:raise ValueError('operation')
        kind=op.get('kind')
        if kind=='submit':
            if set(op)!={'kind','parent','action','seed'} or type(op['action']) is not int or not 0<=op['action']<6 or type(op['seed']) is not int or not 0<=op['seed']<2**32 or Cascade(42).evaluate(op['parent']).stage!=3:raise ValueError('invalid task')
            ident=digest([s['campaign'],op['parent'],op['action'],op['seed']])
            if ident in out['tasks'] or len(out['tasks'])>=MAX_TASKS:raise ValueError('duplicate or full task ledger')
            out['tasks'][ident]={'parent':op['parent'],'action':op['action'],'seed':op['seed'],'attempt':0,'worker':None,'expires':0,'result':None}
            changed.add(ident)
        elif kind=='assign':
            if set(op)!={'kind','task','worker'} or op['worker'] not in s['members'] or op['task'] not in out['tasks'] or op['task'] in changed:raise ValueError('invalid assignment')
            t=out['tasks'][op['task']]
            if t['result'] is not None or height<t['expires'] or t['attempt']>=8 or out['spent']>=s['budget']:raise ValueError('lease or budget exhausted')
            t.update(worker=op['worker'],attempt=t['attempt']+1,expires=height+s['lease_heights']);out['spent']+=1;changed.add(op['task'])
        elif kind=='complete':
            if set(op)!={'kind','result'}:raise ValueError('completion')
            raw=op['result'];v=_envelope(raw);ident=v.get('task')
            if not _hex(ident) or ident not in s['tasks'] or ident in changed or v.get('worker') not in s['members']:raise ValueError('completion identity')
            verify(v['worker'],v,raw['signature']);expected=_result_body(s,ident,v['worker'])
            if v!=expected:raise ValueError('forged or stale result')
            out['tasks'][ident]['result']=raw;changed.add(ident)
        elif kind=='reconfigure':
            if set(op)!={'kind','members','faults'} or len(ops)!=1 or type(op['members']) is not list:raise ValueError('reconfiguration must be isolated')
            _membership(op['members'],op['faults'])
            if not set(op['members'])<=set(s['eligible']):raise ValueError('unregistered validator')
            out['members']=op['members'];out['faults']=op['faults']
        else:raise ValueError('unsupported operation')
    out['height']=height+1;out['parent']=digest(b);return out


def make_block(s,ops):
    b={'header':_header(s),'ops':_wire(ops)};_apply(s,b);return b


def recover_ops(s,available):
    if type(available) is not tuple or len(set(available))!=len(available) or not set(available)<=set(s['members']):raise ValueError('available validators')
    avail=sorted(available);remaining=s['budget']-s['spent'];out=[]
    if not avail:return out
    for ident,t in sorted(s['tasks'].items()):
        if len(out)>=min(MAX_OPS,remaining):break
        if t['result'] is None and s['height']>=t['expires'] and t['attempt']<8:
            workers=[x for x in avail if x!=t['worker']] or avail
            out.append({'kind':'assign','task':ident,'worker':workers[int(ident[:8],16)%len(workers)]})
    return out


def _vote_body(s,round,phase,value,signer):
    if type(round) is not int or not 0<=round<MAX_ROUND or phase not in ('prevote','precommit') or not _hex(value) or signer not in s['members']:raise ValueError('vote bounds')
    return {**_header(s),'round':round,'phase':phase,'value':value,'voter':signer}


def quorum(s,votes,*,phase):
    if type(votes) not in (tuple,list) or not len(s['members'])-s['faults']<=len(votes)<=len(s['members']):raise ValueError('quorum unavailable')
    seen=set();round=None;value=None
    for raw in votes:
        b=_envelope(raw)
        if b!=_vote_body(s,b['round'],phase,b['value'],b['voter']) or b['voter'] in seen:raise ValueError('vote binding')
        verify(b['voter'],b,raw['signature']);seen.add(b['voter'])
        if round is None:round=b['round'];value=b['value']
        if round!=b['round'] or value!=b['value']:raise ValueError('conflicting quorum votes')
    return {'phase':phase,'round':round,'value':value,'votes':sorted(votes,key=lambda r:r['body']['voter'])}


def _qc(s,q,phase,value=None):
    if type(q) is not dict or q!=quorum(s,q['votes'],phase=phase) or (value is not None and q['value']!=value):raise ValueError('invalid quorum certificate')
    return q


def _valid(s,v,round):
    if v is None:return None
    if type(v) is not dict or set(v)!={'block','qc'}:raise ValueError('locked value')
    _apply(s,v['block']);q=_qc(s,v['qc'],'prevote',digest(v['block']))
    if q['round']>=round:raise ValueError('prior round proof required')
    return v



def timeout_quorum(s, votes, round):
    """A timeout is not a vote for a block; quorum authorizes only round change."""
    if type(round) is not int or not 0 <= round < MAX_ROUND-1 or type(votes) not in (list,tuple) or not len(s['members'])-s['faults'] <= len(votes) <= len(s['members']):
        raise ValueError('timeout quorum unavailable')
    seen=set()
    for raw in votes:
        b=_envelope(raw); who=b.get('voter')
        if who not in s['members'] or who in seen or b != {**_header(s),'round':round,'phase':'timeout','voter':who}:
            raise ValueError('timeout binding')
        verify(who,b,raw['signature']);seen.add(who)
    return {'round':round,'votes':sorted(votes,key=lambda v:v['body']['voter'])}


class Replica:
    def __init__(self,path,key,genesis,identity,*,create=False):
        if not isinstance(genesis,Genesis) or not isinstance(identity,Identity) or identity.public not in genesis.eligible:raise ValueError('replica identity')
        self.path=Path(path).absolute();self.g=genesis;self.identity=identity;self.store=CheckpointStore(self.path,key)
        if create:self.store.initialize({'genesis':genesis.id,'identity':identity.public,'state':initial(genesis),'round':0,'locked':None,'votes':{},'timeouts':{},'log':[]})
        self._load()
    def _load(self):
        rev,d=self.store.load()
        if d['genesis']!=self.g.id or d['identity']!=self.identity.public:raise ValueError('replica contract mismatch')
        return rev,d
    def inspect(self):return self._load()[1]
    def _active(self,d):
        if self.identity.public not in d['state']['members'] or d['state']['height']>MAX_HEIGHT:raise ValueError('not an active validator')
    def status(self):
        d=self.inspect();self._active(d);s=d['state'];v=d['locked']
        # A same-round lock can be advertised, but only prior-round QC is
        # eligible as a next-round justification.
        if v is not None and v['qc']['round']>=d['round']:v=None
        return _signed(self.identity,{**_header(s),'round':d['round'],'voter':self.identity.public,'valid':v})
    def advance(self):
        with _lock(self.path):
            rev,d=self._load();self._active(d)
            if d['round']+1>=MAX_ROUND:raise ValueError('round budget exhausted')
            d['round']+=1;self.store.save(rev+1,d)
        return self.status()
    def timeout_vote(self):
        with _lock(self.path):
            rev,d=self._load();self._active(d);r=d['round'];s=d['state']
            if r>=MAX_ROUND-1:raise ValueError('round budget exhausted')
            key=f'{r}:timeout';old=d['votes'].get(key)
            if old is not None:return old
            raw=_signed(self.identity,{**_header(s),'round':r,'phase':'timeout','voter':self.identity.public})
            d['votes'][key]=raw;self.store.save(rev+1,d);return raw
    def advance_certified(self,cert):
        with _lock(self.path):
            rev,d=self._load();self._active(d);r=d['round']
            if type(cert) is not dict or set(cert)!={'round','votes'} or cert['round']!=r or cert!=timeout_quorum(d['state'],cert['votes'],r):raise ValueError('invalid timeout certificate')
            d['timeouts'][str(r)]=cert;d['round']+=1;self.store.save(rev+1,d)
        return self.status()
    def view(self,height,round):
        if type(height) is not int or not 1<=height<=MAX_HEIGHT or type(round) is not int or not 0<=round<MAX_ROUND:raise ValueError('view bounds')
        d=self.inspect();s=d['state']
        if height<s['height']:return {'commit':d['log'][height-1],'timeout_vote':None,'timeout_certificate':None}
        if height>s['height']:return {'commit':None,'timeout_vote':None,'timeout_certificate':None}
        return {'commit':None,'timeout_vote':d['votes'].get(f'{round}:timeout'),'timeout_certificate':d['timeouts'].get(str(round))}
    def propose(self,block,statuses):
        with _lock(self.path):
            rev,d=self._load();self._active(d);s=d['state'];r=d['round'];_apply(s,block)
            if self.identity.public!=leader(s,r) or type(statuses) not in (tuple,list) or not len(s['members'])-s['faults']<=len(statuses)<=len(s['members']):raise ValueError('leader or round quorum missing')
            values=[];seen=set()
            for raw in statuses:
                b=_envelope(raw);who=b['voter']
                if who not in s['members'] or who in seen or b!={**_header(s),'round':r,'voter':who,'valid':b['valid']}:raise ValueError('round report binding')
                verify(who,b,raw['signature']);seen.add(who);v=_valid(s,b['valid'],r)
                if v is not None:values.append(v)
            if d['locked'] is not None and d['locked']['qc']['round']<r:values.append(_valid(s,d['locked'],r))
            prior=max(values,key=lambda v:v['qc']['round']) if values else None
            if prior:block=prior['block']
            body={**_header(s),'round':r,'leader':self.identity.public,'block':block,'prior':prior['qc'] if prior else None}
            key=f'{r}:proposal';old=d['votes'].get(key)
            if old is not None:
                if old['body']!=body:raise ValueError('leader equivocation')
                return old
            raw=_signed(self.identity,body);d['votes'][key]=raw;self.store.save(rev+1,d);return raw
    def _record_vote(self,rev,d,phase,value,*,lock=None):
        s=d['state'];r=d['round'];key=f'{r}:{phase}';body=_vote_body(s,r,phase,value,self.identity.public);old=d['votes'].get(key)
        if old is not None:
            if old['body']!=body:raise ValueError('durable vote conflict')
            return old
        raw=_signed(self.identity,body);d['votes'][key]=raw
        if lock is not None:d['locked']=lock
        self.store.save(rev+1,d);return raw
    def prevote(self,proposal):
        with _lock(self.path):
            rev,d=self._load();self._active(d);s=d['state'];r=d['round'];b=_envelope(proposal);block=b['block'];_apply(s,block);value=digest(block);prior=b['prior']
            if b!={**_header(s),'round':r,'leader':leader(s,r),'block':block,'prior':prior}:raise ValueError('proposal binding')
            verify(b['leader'],b,proposal['signature'])
            if prior is not None:
                _qc(s,prior,'prevote',value)
                if prior['round']>=r:raise ValueError('invalid justification round')
            locked=d['locked']
            if locked is not None and digest(locked['block'])!=value and (prior is None or prior['round']<locked['qc']['round']):raise ValueError('locked on different value')
            return self._record_vote(rev,d,'prevote',value)
    def precommit(self,block,pv):
        with _lock(self.path):
            rev,d=self._load();self._active(d);s=d['state'];_apply(s,block);value=digest(block);_qc(s,pv,'prevote',value)
            if pv['round']!=d['round']:raise ValueError('precommit round mismatch')
            return self._record_vote(rev,d,'precommit',value,lock={'block':block,'qc':pv})
    def commit(self,block,pv,pc):
        with _lock(self.path):
            rev,d=self._load();s=d['state'];h=block['header']['height'];value=digest(block)
            if type(h) is not int or h<1:raise ValueError('height')
            if h<s['height']:
                old=d['log'][h-1]
                if old['block']!=block:raise ValueError('conflicting committed value')
                # Already committed this value; no new certificate or state is admitted.
                return False
            out=_apply(s,block);_qc(s,pv,'prevote',value);_qc(s,pc,'precommit',value)
            if pv['round']!=pc['round']:raise ValueError('commit round mismatch')
            d['log'].append({'block':block,'prevote':pv,'precommit':pc});d.update(state=out,round=0,locked=None,votes={},timeouts={});self.store.save(rev+1,d);return True
    def sync(self,records):
        if type(records) is not list or len(records)>MAX_HEIGHT:raise ValueError('sync bounds')
        for r in records:self.commit(r['block'],r['prevote'],r['precommit'])
        return self.inspect()['state']


def export_completed(s,identity,recipient,sequence,*,limit=8):
    from .federation import _qualified
    if not isinstance(identity,Identity) or identity.public not in s['members'] or type(limit) is not int or not 1<=limit<=8:raise ValueError('export bounds')
    codes=[]
    for t in s['tasks'].values():
        if t['result'] is not None:
            b=_envelope(t['result']);verify(b['worker'],b,t['result']['signature'])
            if b['stage']==3 and b['metrics'][3]==1.:
                _qualified(b['code']);codes.append(b['code'])
    return packet(identity,recipient,sequence,tuple(dict.fromkeys(codes))[:limit])
