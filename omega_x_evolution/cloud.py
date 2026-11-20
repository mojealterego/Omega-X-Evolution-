"""Explicitly authorized, budgeted Kubernetes GPU/TPU workload orchestration.

The cluster and its autoscaler, quota/admission policy and approved image are
operator-owned. Reservations are configured cost ceilings, not cloud invoices.
No action creates a cluster, buys capacity, grants IAM rights, or runs forever.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import http.client
import json
import re
import ssl
from pathlib import Path
from urllib.parse import urlsplit
from .checkpoint import CheckpointStore
from .infrastructure import _lock
from .graph_memory import canonical

API_SLOTS=9  # one POST, four normal GETs, four emergency cleanup operations
MAX_RESPONSE=2*1024*1024
NAME=re.compile(r'[a-z][a-z0-9-]{0,62}')


def _hash(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def _name(s):return type(s) is str and NAME.fullmatch(s) is not None and not s.endswith('-')
def _hex(s):return type(s) is str and re.fullmatch(r'[0-9a-f]{64}',s) is not None


@dataclass(frozen=True)
class Policy:
    namespace:str
    image:str
    total_micros:int
    cpu_hour_micros:int
    gpu_hour_micros:int
    tpu_hour_micros:int
    api_call_micros:int=0
    max_jobs:int=8
    max_replicas:int=8
    max_wall_seconds:int=3600
    tpu_accelerator:str=''
    tpu_topology:str=''
    def __post_init__(self):
        if not _name(self.namespace) or type(self.image) is not str or not re.fullmatch(r'[a-zA-Z0-9./:_-]{1,240}@sha256:[0-9a-f]{64}',self.image):raise ValueError('namespace or image digest')
        values=(self.total_micros,self.cpu_hour_micros,self.gpu_hour_micros,self.tpu_hour_micros,self.api_call_micros,self.max_jobs,self.max_replicas,self.max_wall_seconds)
        if any(type(x) is not int for x in values) or not 1<=self.total_micros<=10**10 or any(not 1<=r<=10**10 for r in values[1:4]) or not 0<=self.api_call_micros<=10**8 or not 1<=self.max_jobs<=32 or not 1<=self.max_replicas<=32 or not 10<=self.max_wall_seconds<=7200:raise ValueError('cloud limits')
        if bool(self.tpu_accelerator)!=bool(self.tpu_topology) or self.tpu_accelerator and (not re.fullmatch(r'[a-z0-9-]{1,63}',self.tpu_accelerator) or not re.fullmatch(r'[0-9]{1,2}x[0-9]{1,2}(x[0-9]{1,2})?',self.tpu_topology)):raise ValueError('TPU topology')


@dataclass(frozen=True)
class Job:
    id:str
    kind:str
    replicas:int
    accelerators:int
    wall_seconds:int
    seed:int
    budget:int
    def __post_init__(self):
        if not _name(self.id) or self.kind not in ('cpu','gpu','tpu') or any(type(x) is not int for x in (self.replicas,self.accelerators,self.wall_seconds,self.seed,self.budget)) or not 1<=self.replicas<=8 or not 10<=self.wall_seconds<=7200 or not 0<=self.seed<2**32-8 or not 16<=self.budget<=1024 or (self.kind=='cpu' and self.accelerators!=0) or (self.kind=='gpu' and self.accelerators!=1) or (self.kind=='tpu' and not 1<=self.accelerators<=8):raise ValueError('job bounds; one GPU per worker, single-host TPU slices only')


def reservation(policy,job):
    if not isinstance(policy,Policy) or not isinstance(job,Job) or job.wall_seconds>policy.max_wall_seconds or job.replicas>policy.max_replicas:raise ValueError('job exceeds policy')
    rate=getattr(policy,job.kind+'_hour_micros');units=job.replicas*max(1,job.accelerators)
    return (job.wall_seconds*rate*units+3599)//3600+API_SLOTS*policy.api_call_micros


def manifest(policy,job,ledger_id):
    reservation(policy,job)
    if not _hex(ledger_id):raise ValueError('ledger identity')
    if job.kind=='tpu' and not policy.tpu_accelerator:raise ValueError('approved TPU topology required')
    name='omega-'+_hash([ledger_id,job.id])[:32];labels={'app.kubernetes.io/name':'omega-x-evolution','omega-run':ledger_id[:32]}
    limits={'cpu':'1','memory':'2Gi'};selector={};tolerations=[]
    if job.kind!='cpu':
        device='nvidia.com/gpu' if job.kind=='gpu' else 'google.com/tpu';limits.update({'cpu':'2','memory':'8Gi',device:str(job.accelerators)});tolerations=[{'key':device,'operator':'Exists','effect':'NoSchedule'}]
    if job.kind=='tpu':selector={'cloud.google.com/gke-tpu-accelerator':policy.tpu_accelerator,'cloud.google.com/gke-tpu-topology':policy.tpu_topology}
    pod={'restartPolicy':'Never','automountServiceAccountToken':False,'enableServiceLinks':False,'terminationGracePeriodSeconds':10,'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'seccompProfile':{'type':'RuntimeDefault'}},'hostNetwork':False,'hostPID':False,'hostIPC':False,'nodeSelector':selector,'tolerations':tolerations,
         'containers':[{'name':'worker','image':policy.image,'imagePullPolicy':'IfNotPresent','command':['python','-m','omega_x_evolution.cloud_worker'],'args':['--kind',job.kind,'--seed',str(job.seed),'--budget',str(job.budget)],'resources':{'requests':dict(limits),'limits':dict(limits)},'securityContext':{'privileged':False,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},'env':[{'name':'PYTHONUNBUFFERED','value':'1'},{'name':'PYTHONDONTWRITEBYTECODE','value':'1'},{'name':'JOB_COMPLETION_INDEX','valueFrom':{'fieldRef':{'fieldPath':"metadata.annotations['batch.kubernetes.io/job-completion-index']"}}}],'volumeMounts':[{'name':'scratch','mountPath':'/tmp'}]}],'volumes':[{'name':'scratch','emptyDir':{'sizeLimit':'256Mi'}}]}
    spec={'parallelism':job.replicas,'completions':job.replicas,'completionMode':'Indexed','activeDeadlineSeconds':job.wall_seconds,'backoffLimit':0,'ttlSecondsAfterFinished':3600,'suspend':False,'template':{'metadata':{'labels':labels},'spec':pod}}
    return {'apiVersion':'batch/v1','kind':'Job','metadata':{'name':name,'namespace':policy.namespace,'labels':labels,'annotations':{'omega-x/spec-sha256':_hash(spec)}},'spec':spec}


def _contains(actual,expected):
    if type(expected) is dict:return type(actual) is dict and all(k in actual and _contains(actual[k],v) for k,v in expected.items())
    if type(expected) is list:return type(actual) is list and len(actual)==len(expected) and all(_contains(a,b) for a,b in zip(actual,expected))
    return type(actual) is type(expected) and actual==expected


def _match(actual,wanted):
    """Fail closed on changed resource identity, runtime bounds or pod template."""
    if type(actual) is not dict or len(canonical(actual).encode())>MAX_RESPONSE:raise ValueError('provider job spec mismatch')
    # The API commonly omits zero-valued scalar/empty map fields when serializing.
    actual=json.loads(canonical(actual))
    try:
        pod=actual['spec']['template']['spec']
        for k in ('hostNetwork','hostPID','hostIPC'):pod.setdefault(k,False)
        pod.setdefault('nodeSelector',{});pod.setdefault('tolerations',[])
    except (KeyError,TypeError,AttributeError) as e:raise ValueError('missing pod template') from e
    if not _contains(actual,wanted):raise ValueError('provider job spec mismatch')
    metadata=actual['metadata'];uid=metadata.get('uid')
    if type(uid) is not str or not 1<=len(uid)<=128:raise ValueError('provider UID missing')
    pod=actual['spec']['template']['spec'];container=pod['containers'][0]
    # A container securityContext takes precedence over its pod defaults.
    # Subset matching alone admits additional, conflicting settings. Permit
    # only the requested policy and explicit security-equivalent API defaults.
    wanted_pod=wanted['spec']['template']['spec']
    if canonical(pod['securityContext'])!=canonical(wanted_pod['securityContext']):
        raise ValueError('unexpected pod security context')
    expected=dict(wanted_pod['containers'][0]['securityContext'])
    defaults={'runAsNonRoot':True,'runAsUser':10001,
              'seccompProfile':{'type':'RuntimeDefault'},'procMount':'Default'}
    observed=container['securityContext']
    expected.update({k:v for k,v in defaults.items() if k in observed})
    if canonical(observed)!=canonical(expected) or pod.get('shareProcessNamespace',False) is not False:
        raise ValueError('unexpected effective container security context')
    if pod.get('initContainers') or pod.get('ephemeralContainers') or pod.get('hostAliases') or container.get('envFrom') or container.get('lifecycle') or container.get('securityContext',{}).get('capabilities',{}).get('add') or any(p.get('hostPort') for p in container.get('ports',[])):raise ValueError('unexpected workload injection')
    return uid


class KubernetesProvider:
    """Actual batch/v1 Job REST client; no discovery, redirects or proxy use."""
    def __init__(self,server,namespace,token,*,ca_file=None):
        u=urlsplit(server)
        if u.scheme!='https' or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment or not _name(namespace) or type(token) is not str or not 16<=len(token)<=16384 or any(c.isspace() for c in token):raise ValueError('trusted HTTPS API configuration required')
        self.host=u.hostname;self.port=u.port or 443;self.namespace=namespace;self._token=token;self.context=ssl.create_default_context(cafile=ca_file);self.context.minimum_version=ssl.TLSVersion.TLSv1_2
        self.identity=_hash([server.rstrip('/'),namespace]);self.path=f'/apis/batch/v1/namespaces/{namespace}/jobs'
    def _request(self,method,name=None,body=None):
        if name is not None and not _name(name):raise ValueError('job name')
        conn=http.client.HTTPSConnection(self.host,self.port,context=self.context,timeout=15)
        try:
            data=None if body is None else canonical(body).encode();conn.request(method,self.path+('/'+name if name else ''),body=data,headers={'Authorization':'Bearer '+self._token,'Content-Type':'application/json','Accept':'application/json'});r=conn.getresponse();raw=r.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError('Kubernetes response cap')
            if r.status==404 and method in ('GET','DELETE'):return None
            if r.status not in (200,201,202):raise RuntimeError(f'Kubernetes API status {r.status}')
            return json.loads(raw) if raw else {}
        finally:conn.close()
    def create(self,body):return self._request('POST',body=body)
    def get(self,name):return self._request('GET',name)
    def delete(self,name,uid):return self._request('DELETE',name,{'apiVersion':'v1','kind':'DeleteOptions','propagationPolicy':'Foreground','preconditions':{'uid':uid}})


class CloudOrchestrator:
    def __init__(self,path,key,policy,provider,*,ledger_id,create=False):
        if not isinstance(policy,Policy) or not _hex(ledger_id) or getattr(provider,'namespace',None)!=policy.namespace or type(getattr(provider,'identity',None)) is not str:raise ValueError('cloud contract')
        self.path=Path(path);self.store=CheckpointStore(path,key);self.policy=policy;self.provider=provider;self.ledger_id=ledger_id;self.contract=_hash(['omega-cloud-v1',asdict(policy),provider.identity,ledger_id,hashlib.sha256(Path(__file__).read_bytes()).hexdigest()])
        if create:self.store.initialize({'contract':self.contract,'stopped':False,'spent_micros':0,'api_calls':0,'jobs':{},'api':{}})
        self.inspect()
    def _load(self):
        rev,s=self.store.load()
        if s['contract']!=self.contract:raise ValueError('cloud ledger mismatch')
        return rev,s
    def inspect(self):return self._load()[1]
    @staticmethod
    def _authorized(v):
        if v is not True:raise PermissionError('explicit cloud action authorization required')
    def _spend(self,s,n):
        if s['stopped'] or s['spent_micros']+n>self.policy.total_micros:raise ValueError('budget exhausted or stopped')
        s['spent_micros']+=n
    def _call(self,rev,s,row,kind,fn,*args):
        key='cleanup_left' if kind=='cleanup' else 'normal_left'
        if row[key]<=0:raise ValueError('reserved API call allowance exhausted')
        row[key]-=1;s['api_calls']+=1;self.store.save(rev+1,s)
        return rev+1,fn(*args)
    def _observed(self,row,actual):
        if actual is None:row['status']='absent';return
        uid=_match(actual,row['manifest'])
        if row['uid'] is not None and uid!=row['uid']:raise ValueError('provider object changed identity')
        row['uid']=uid
        conditions=actual.get('status',{}).get('conditions',[])
        terminal=next((c['type'] for c in conditions if c.get('type') in ('Complete','Failed') and c.get('status')=='True'),None)
        row['status']=terminal.lower() if terminal else ('delete_requested' if actual['metadata'].get('deletionTimestamp') else 'active')
    def submit(self,job,*,authorized=False):
        self._authorized(authorized);wanted=manifest(self.policy,job,self.ledger_id);cost=reservation(self.policy,job)
        with _lock(self.path):
            rev,s=self._load();old=s['jobs'].get(job.id)
            if old:
                if old['job']!=asdict(job):raise ValueError('conflicting job id')
                return old
            active=sum(r['job']['replicas'] for r in s['jobs'].values() if r['status'] not in ('absent','complete','failed'))
            if len(s['jobs'])>=self.policy.max_jobs or active+job.replicas>self.policy.max_replicas:raise ValueError('job/replica budget')
            self._spend(s,cost);row={'job':asdict(job),'manifest':wanted,'reserved_micros':cost,'uid':None,'status':'reserved','normal_left':4,'cleanup_left':4};s['jobs'][job.id]=row;s['api_calls']+=1;self.store.save(rev+1,s);rev+=1
            # No blind retry: reserved state remains if response is lost.
            actual=self.provider.create(wanted);self._observed(row,actual)
            if row['uid'] is None:raise ValueError('missing create response')
            self.store.save(rev+1,s);return row
    def reconcile(self,job_id,*,authorized=False):
        self._authorized(authorized)
        with _lock(self.path):
            rev,s=self._load();row=s['jobs'][job_id];rev,actual=self._call(rev,s,row,'normal',self.provider.get,row['manifest']['metadata']['name']);self._observed(row,actual);self.store.save(rev+1,s);return row
    def stop(self,*,authorized=False):
        self._authorized(authorized)
        with _lock(self.path):
            rev,s=self._load()
            if not s['stopped']:s['stopped']=True;self.store.save(rev+1,s);rev+=1
            errors=[]
            for ident in list(s['jobs']):
                # Each failed call has already been durably charged. Reload
                # between jobs to preserve the revision after network errors.
                rev,s=self._load();row=s['jobs'][ident]
                if row['status'] in ('absent','complete','failed'):continue
                try:
                    name=row['manifest']['metadata']['name'];rev,actual=self._call(rev,s,row,'cleanup',self.provider.get,name);self._observed(row,actual);self.store.save(rev+1,s);rev+=1
                    if row['status'] in ('absent','complete','failed'):continue
                    rev,_=self._call(rev,s,row,'cleanup',self.provider.delete,name,row['uid']);row['status']='delete_requested';self.store.save(rev+1,s)
                except (OSError,ValueError,RuntimeError,KeyError,http.client.HTTPException):errors.append(ident)
            _,s=self._load();return {'stopped':s['stopped'],'delete_errors':errors,'jobs':{k:r['status'] for k,r in s['jobs'].items()}}
    def reserve_api(self,request_id,max_units,unit_micros,*,authorized=False):
        self._authorized(authorized)
        if not _name(request_id) or type(max_units) is not int or not 1<=max_units<=1_000_000 or type(unit_micros) is not int or not 1<=unit_micros<=1_000_000:raise ValueError('API reservation bounds')
        with _lock(self.path):
            rev,s=self._load();old=s['api'].get(request_id)
            if old:
                if (old['max_units'],old['unit_micros'])!=(max_units,unit_micros):raise ValueError('conflicting API reservation')
                return old
            if len(s['api'])>=128:raise ValueError('API reservation count')
            amount=max_units*unit_micros;self._spend(s,amount);row={'max_units':max_units,'unit_micros':unit_micros,'reserved_micros':amount,'used_units':None};s['api'][request_id]=row;self.store.save(rev+1,s);return row
    def settle_api(self,request_id,used_units,*,authorized=False):
        self._authorized(authorized)
        if type(used_units) is not int or not 0<=used_units<=10**9:raise ValueError('actual usage bounds')
        with _lock(self.path):
            rev,s=self._load();row=s['api'][request_id]
            if row['used_units'] is not None:
                if row['used_units']!=used_units:raise ValueError('conflicting settlement')
                return row
            row['used_units']=used_units
            if used_units>row['max_units']:row['overrun_micros']=(used_units-row['max_units'])*row['unit_micros'];s['spent_micros']+=row['overrun_micros'];s['stopped']=True
            self.store.save(rev+1,s);return row


def main():
    """Operator-controlled cloud ledger CLI; no autonomous provisioning on import."""
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,required=True);p.add_argument('--key-file',type=Path,required=True)
    p.add_argument('--policy',type=Path,required=True);p.add_argument('--server',required=True)
    p.add_argument('--token-file',type=Path,required=True);p.add_argument('--ca-file',type=Path)
    p.add_argument('--ledger-id',required=True);p.add_argument('--create',action='store_true');p.add_argument('--authorize',action='store_true')
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('inspect');q=sub.add_parser('submit');q.add_argument('job',type=Path)
    q=sub.add_parser('reconcile');q.add_argument('job_id');sub.add_parser('stop')
    q=sub.add_parser('reserve-api');q.add_argument('request_id');q.add_argument('max_units',type=int);q.add_argument('unit_micros',type=int)
    q=sub.add_parser('settle-api');q.add_argument('request_id');q.add_argument('used_units',type=int)
    a=p.parse_args()
    if (a.create or a.action!='inspect') and not a.authorize:p.error('explicit --authorize required')
    def read(path,cap):
        with path.open('rb') as f:data=f.read(cap+1)
        if not 1<=len(data)<=cap:raise ValueError('configuration file bounds')
        return data
    policy=Policy(**json.loads(read(a.policy,16384)))
    provider=KubernetesProvider(a.server,policy.namespace,read(a.token_file,16384).decode().strip(),ca_file=str(a.ca_file) if a.ca_file else None)
    controller=CloudOrchestrator(a.db,read(a.key_file,4096),policy,provider,ledger_id=a.ledger_id,create=a.create)
    if a.action=='inspect':out=controller.inspect()
    elif a.action=='submit':out=controller.submit(Job(**json.loads(read(a.job,16384))),authorized=True)
    elif a.action=='reconcile':out=controller.reconcile(a.job_id,authorized=True)
    elif a.action=='stop':out=controller.stop(authorized=True)
    elif a.action=='reserve-api':out=controller.reserve_api(a.request_id,a.max_units,a.unit_micros,authorized=True)
    else:out=controller.settle_api(a.request_id,a.used_units,authorized=True)
    print(json.dumps(out,indent=2,allow_nan=False))


if __name__=='__main__':main()
