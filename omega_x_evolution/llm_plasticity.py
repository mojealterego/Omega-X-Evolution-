"""Live low-rank transformer adaptation on verified evolution trajectories.

The small built-in CPU fixture is a real decoder, not a pretrained LLM.
A local safetensors-only Hugging Face causal LM is an explicit optional backend.
The model proposes only one of six typed mutation operators; never executes code.
"""
from __future__ import annotations
import argparse
import ast
import base64
import hashlib
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace
from .checkpoint import CheckpointStore
from .graph_memory import canonical
from .infrastructure import _lock
from . import plasticity
from .engine import Audit, BASELINE, Cascade, Expression, apply_patch, score
from .annealed import propose
from .holographic import trajectory

MAX_ADAPTER=1_000_000
MAX_TOKENS=512


def _digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def _context(code):return ast.dump(Expression(code).tree,include_attributes=False)


class Session:
    def __init__(self,model,encoder,action_ids,*,encoder_id,device='cpu',rank=2,seed=42):
        import torch
        from torch import nn
        if device not in ('cpu','cuda') or type(rank) is not int or not 1<=rank<=8 or type(seed) is not int or not 0<=seed<2**32 or type(action_ids) is not tuple or len(action_ids)!=6 or len(set(action_ids))!=6 or any(type(i) is not int or i<0 for i in action_ids) or not isinstance(encoder_id,str) or len(encoder_id)!=64:raise ValueError('transformer contract')
        if device=='cuda' and not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
        if not isinstance(model,nn.Module) or not callable(encoder):raise ValueError('local trusted model required')
        frozen=sum(p.numel() for p in model.parameters())
        if not 1<=frozen<=4_000_000_000:raise ValueError('model parameter cap')
        if device=='cuda':
            free,_=torch.cuda.mem_get_info();size=sum(p.numel()*p.element_size() for p in model.parameters())
            if size*1.5>free:raise RuntimeError('insufficient free CUDA memory')
        self.model=model.to(device);self.encoder=encoder;self.action_ids=action_ids;self.device=device;self.rank=rank;self.encoder_id=encoder_id;self.frozen=frozen;self.microbatch=1 if frozen>=10_000_000 else 64
        for p in model.parameters():p.requires_grad_(False)
        generator=torch.Generator(device='cpu').manual_seed(seed)
        class LowRank(nn.Module):
            def __init__(self,base):
                super().__init__();self.base=base
                self.lora_a=nn.Parameter(torch.randn((rank,base.in_features),generator=generator,dtype=torch.float32).to(device)*.01)
                self.lora_b=nn.Parameter(torch.zeros((base.out_features,rank),device=device,dtype=torch.float32))
            def forward(self,x):
                update=torch.nn.functional.linear(torch.nn.functional.linear(x.float(),self.lora_a),self.lora_b)
                return self.base(x)+update.to(x.dtype)
        targets=[(name,m) for name,m in model.named_modules() if name.rsplit('.',1)[-1] in ('q_proj','v_proj') and isinstance(m,nn.Linear)]
        if not targets or sum(rank*(m.in_features+m.out_features) for _,m in targets)>MAX_ADAPTER:raise ValueError('no supported projections or adapter cap exceeded')
        for name,m in targets:
            prefix,_,leaf=name.rpartition('.');parent=model.get_submodule(prefix) if prefix else model;setattr(parent,leaf,LowRank(m))
        self.params={n:p for n,p in model.named_parameters() if p.requires_grad};self.trainable=sum(p.numel() for p in self.params.values());model.eval()
        self.base_sha=self.base_digest();self.initial=self.snapshot()

    def base_digest(self):
        import torch
        h=hashlib.sha256()
        for n,t in sorted(self.model.state_dict().items()):
            if n in self.params:continue
            h.update(canonical([n,list(t.shape),str(t.dtype)]).encode());flat=t.detach().reshape(-1)
            for i in range(0,flat.numel(),1_000_000):h.update(flat[i:i+1_000_000].cpu().contiguous().view(torch.uint8).numpy().tobytes())
        return h.hexdigest()

    def snapshot(self):
        return {n:{'shape':list(p.shape),'data':base64.b64encode(p.detach().cpu().contiguous().numpy().astype('<f4',copy=False).tobytes()).decode('ascii')} for n,p in sorted(self.params.items())}

    def restore(self,value):
        import numpy as np
        import torch
        if type(value) is not dict or set(value)!=set(self.params):raise ValueError('adapter keys')
        decoded={}
        for n,p in self.params.items():
            row=value[n]
            if type(row) is not dict or set(row)!={'shape','data'} or row['shape']!=list(p.shape) or type(row['data']) is not str or len(row['data'])>4*p.numel()*2:raise ValueError('adapter tensor shape')
            raw=base64.b64decode(row['data'],validate=True)
            if len(raw)!=4*p.numel():raise ValueError('adapter byte count')
            a=np.frombuffer(raw,dtype='<f4').copy().reshape(row['shape'])
            if not np.isfinite(a).all() or np.max(np.abs(a))>10:raise ValueError('adapter values')
            decoded[n]=torch.from_numpy(a).to(self.device)
        with torch.no_grad():
            for n,p in self.params.items():p.copy_(decoded[n])

    def _batch(self,codes):
        import torch
        enc=[]
        for c in codes:
            Expression(c);ids=self.encoder(c)
            if type(ids) not in (list,tuple) or not 1<=len(ids)<=MAX_TOKENS or any(type(x) is not int or x<0 for x in ids):raise ValueError('tokenized context outside cap')
            enc.append(list(ids))
        length=max(map(len,enc));positions=torch.tensor([len(x)-1 for x in enc],device=self.device,dtype=torch.long)
        tokens=torch.tensor([x+[0]*(length-len(x)) for x in enc],device=self.device,dtype=torch.long);mask=torch.tensor([[1]*len(x)+[0]*(length-len(x)) for x in enc],device=self.device,dtype=torch.long)
        return tokens,mask,positions

    def _values(self,batch):
        import torch
        tokens,mask,pos=batch;out=self.model(input_ids=tokens,attention_mask=mask,use_cache=False).logits
        logits=out[torch.arange(len(pos),device=self.device),pos][:,list(self.action_ids)].float()
        if not torch.isfinite(logits).all():raise ValueError('nonfinite logits')
        return torch.tanh((logits-logits.mean(dim=1,keepdim=True))/4.)

    def action(self,code,rng):
        import torch
        with torch.no_grad():v=self._values(self._batch([code]))[0]
        return rng.randrange(6) if rng.random()<.2 else int(v.argmax().item())

    def _dataset(self,rows):
        import torch
        return self._batch([r['parent'] for r in rows]),torch.tensor([r['action'] for r in rows],device=self.device,dtype=torch.long),torch.tensor([r['reward'] for r in rows],device=self.device,dtype=torch.float32)

    def _loss(self,data):
        import torch
        b,a,y=data;v=self._values(b);return ((v[torch.arange(len(a),device=self.device),a]-y)**2).mean()

    def _chunks(self,data):
        b,a,y=data
        if type(self.microbatch) is not int or not 1<=self.microbatch<=64:raise ValueError('microbatch bound')
        for i in range(0,len(a),self.microbatch):
            part=slice(i,i+self.microbatch)
            yield (tuple(x[part] for x in b),a[part],y[part]),len(a[part])/len(a)

    def _mean_loss(self,data):
        return sum(float(self._loss(chunk).item())*weight for chunk,weight in self._chunks(data))

    def _backward(self,data):
        # Aggregate gradients with exact sample-count weighting. Each graph is
        # freed before the next microbatch, rather than retaining all logits.
        total=0.
        for chunk,weight in self._chunks(data):
            loss=self._loss(chunk)*weight
            total+=float(loss.detach().item());loss.backward()
        return total

    def evaluate(self,rows):
        import torch
        if type(rows) is not tuple or not 1<=len(rows)<=64:raise ValueError('test bound')
        rows=tuple(plasticity.validate_record(r) for r in rows)
        with torch.no_grad():return self._mean_loss(self._dataset(rows))

    def fit(self,train,validation,retention,*,steps=8,learning_rate=.01):
        import torch
        if type(steps) is not int or not 1<=steps<=64 or type(learning_rate) not in (int,float) or not 0<learning_rate<=.05:raise ValueError('training bounds')
        groups=plasticity._prepare((train,validation,retention));data=[self._dataset(g) for g in groups];prior=self.snapshot()
        if self.base_digest()!=self.base_sha:raise ValueError('base model changed')
        def losses():
            with torch.no_grad():return [self._mean_loss(d) for d in data]
        before=losses()
        # Reference evaluation temporarily replaces the active adapter. Restore
        # it even if inference fails before the optimizer is constructed.
        try:
            self.restore(self.initial)
            root=losses()[2]
        finally:
            self.restore(prior)
        opt=torch.optim.AdamW(list(self.params.values()),lr=learning_rate,weight_decay=0.)
        try:
            for _ in range(steps):
                opt.zero_grad(set_to_none=True);self._backward(data[0]);torch.nn.utils.clip_grad_norm_(list(self.params.values()),1.,error_if_nonfinite=True);opt.step()
            candidate=self.snapshot();self.restore(candidate);after=losses()
            if not all(math.isfinite(x) for x in before+after) or self.base_digest()!=self.base_sha:raise ValueError('nonfinite training or changed base')
            promoted=after[1]<before[1]-1e-9 and after[2]<=min(root,before[2])+.002
            if not promoted:self.restore(prior)
            return {'actual_steps':steps,'train_before':before[0],'train_after':after[0],'validation_before':before[1],'validation_candidate':after[1],'retention_before':before[2],'retention_candidate':after[2],'promoted':promoted,'candidate_sha256':_digest(candidate),'active_sha256':_digest(self.snapshot())}
        except BaseException:self.restore(prior);raise
        finally:opt.zero_grad(set_to_none=True)


def model_manifest(path):
    """Inspect local safe tensor headers and shard index before allocating weights."""
    from safetensors import safe_open
    path=Path(path).resolve(strict=True)
    files=tuple(sorted(path.glob('*.safetensors'))) if path.is_dir() else ()
    if not files or len(files)>128 or any(x.is_symlink() or not x.is_file() for x in files):raise ValueError('local safetensors required')
    size=sum(x.stat().st_size for x in files)
    if not 0<size<=16_000_000_000:raise ValueError('local model byte cap')
    config=path/'config.json'
    if not config.is_file() or config.is_symlink() or config.stat().st_size>1_048_576:raise ValueError('local model config')
    config_bytes=config.read_bytes();cfg=json.loads(config_bytes)
    if type(cfg) is not dict or cfg.get('auto_map'):raise ValueError('untrusted model code')
    weights={};records=[];elements=0
    for f in files:
        with safe_open(str(f),framework='pt',device='cpu') as obj:
            for name in obj.keys():
                if name in weights or len(weights)>=100_000:raise ValueError('duplicate or excessive tensor keys')
                info=obj.get_slice(name);shape=info.get_shape();dtype=info.get_dtype()
                if dtype not in ('F16','BF16','F32','F64','I64','I32','I16','I8','U8','BOOL') or len(shape)>8 or any(type(x) is not int or x<0 for x in shape):raise ValueError('tensor metadata')
                elements+=math.prod(shape);weights[name]=f.name
                if elements>4_000_000_000:raise ValueError('model parameter cap')
        h=hashlib.sha256()
        with f.open('rb') as stream:
            for chunk in iter(lambda:stream.read(4*1024*1024),b''):h.update(chunk)
        records.append({'name':f.name,'bytes':f.stat().st_size,'sha256':h.hexdigest()})
    idx=path/'model.safetensors.index.json'
    if idx.exists() or len(files)>1:
        if not idx.is_file() or idx.is_symlink() or idx.stat().st_size>16*1024*1024:raise ValueError('shard index required')
        mapping=json.loads(idx.read_bytes()).get('weight_map')
        if mapping!=weights:raise ValueError('shard index does not match exact local tensors')
    if elements<1:raise ValueError('empty model')
    return {'parameter_elements':elements,'storage_bytes':size,'config_sha256':hashlib.sha256(config_bytes).hexdigest(),'files':records}


def memory_admission(info,*,device,available_bytes=None):
    """Conservative weight/loading estimate, not an allocator or hardware proof."""
    import torch
    if device not in ('cpu','cuda'):raise ValueError('device')
    if available_bytes is None:
        if device=='cuda':
            if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable')
            available_bytes=torch.cuda.mem_get_info()[0]
        else:
            import psutil
            available_bytes=psutil.virtual_memory().available
            try:
                limit=Path('/sys/fs/cgroup/memory.max').read_text().strip()
                if limit!='max':available_bytes=min(available_bytes,max(0,int(limit)-int(Path('/sys/fs/cgroup/memory.current').read_text())))
            except (OSError,ValueError):pass
    if type(available_bytes) is not int or available_bytes<0 or type(info.get('parameter_elements')) is not int or not 1<=info['parameter_elements']<=4_000_000_000 or type(info.get('storage_bytes')) is not int or not 1<=info['storage_bytes']<=16_000_000_000:raise ValueError('memory admission metadata')
    weights=info['parameter_elements']*(2 if device=='cuda' else 4)
    # Weight conversion/loading, one microbatch, inference scratch and adapter.
    # Actual activations depend on the model: caller must still enforce OS limits.
    required=max(2*weights,weights+info['storage_bytes'])+256*1024*1024
    if required>available_bytes*3//4:raise RuntimeError('memory admission rejected local model')
    return {'admitted':True,'estimated_bytes':required,'available_bytes':available_bytes,'device':device,'microbatch':1}


def load_local(path,*,device='cuda',rank=2,seed=42,backend='transformers'):
    """Operator-provided local model; no network or remote model code permitted."""
    import torch
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise RuntimeError('requested device unavailable')
    path=Path(path).resolve(strict=True)
    if backend not in ('transformers','native-llama'):raise ValueError('local model backend')
    manifest=model_manifest(path);memory_admission(manifest,device=device)
    if backend=='native-llama':
        from .native_llama import _load_session
        return _load_session(path,manifest,device=device,rank=rank,seed=seed)
    from transformers import AutoModelForCausalLM,AutoTokenizer
    tok=AutoTokenizer.from_pretrained(str(path),trust_remote_code=False,local_files_only=True)
    ids=tuple(tok.encode(str(i),add_special_tokens=False) for i in range(6))
    if any(len(x)!=1 for x in ids):raise ValueError('operator tokens must be single distinct tokens')
    model=AutoModelForCausalLM.from_pretrained(str(path),local_files_only=True,trust_remote_code=False,use_safetensors=True,torch_dtype=torch.float16 if device=='cuda' else torch.float32)
    encode=lambda code:tok.encode('Select one mutation operator (0-5) for expression: '+code+'\nOperator: ',add_special_tokens=True)
    # Bind the full serialized tokenizer implementation when fast; slow tokenizers
    # are rejected rather than relying only on their vocabulary.
    if not getattr(tok,'is_fast',False):raise ValueError('fast tokenizer required for contract')
    encoder_id=hashlib.sha256(tok.backend_tokenizer.to_str().encode()).hexdigest()
    session=Session(model,encode,tuple(x[0] for x in ids),encoder_id=encoder_id,device=device,rank=rank,seed=seed)
    session.microbatch=1;session.local_manifest=manifest
    return session


class OnlineCampaign:
    def __init__(self,path,key,session,validation,retention,*,rounds=4,batch=4,steps=8,seed=42,create=False):
        if not isinstance(session,Session) or any(type(v) is not int for v in (rounds,batch,steps,seed)) or not 1<=rounds<=8 or not 1<=batch<=8 or not 1<=steps<=64 or not 0<=seed<2**32:raise ValueError('campaign bounds')
        self.path=Path(path);self.key=key;self.session=session;self.validation,self.retention=plasticity._prepare((validation,retention));self.excluded={_context(r['parent']) for r in (*self.validation,*self.retention)};self.store=CheckpointStore(path,key);self.rounds=rounds;self.batch=batch;self.steps=steps;self.seed=seed
        if _context(BASELINE) in self.excluded:raise ValueError('evaluation split contains seed')
        root=Path(__file__).parent;self.contract=_digest([session.base_sha,session.encoder_id,session.action_ids,session.rank,session.device,session.microbatch,rounds,batch,steps,seed,self.validation,self.retention,*[hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ('llm_plasticity.py','plasticity.py','engine.py','annealed.py','safety_synthesis.py','interval_checker.py','modal.py')]])
        if create:self.store.initialize({'contract':self.contract,'active':session.initial,'parents':[BASELINE],'rounds':0,'history':[],'spent_steps':0,'attempts':0,'pending':None,'rollbacks':0})
        self.inspect()
    def _load(self):
        rev,s=self.store.load()
        if s['contract']!=self.contract:raise ValueError('live campaign mismatch')
        self.session.restore(s['active']);return rev,s
    def inspect(self):return self._load()[1]
    def step(self,*,authorized=False):
        if authorized is not True:raise PermissionError('explicit training authorization required')
        with _lock(self.path):
            rev,s=self._load()
            if s['pending'] is not None:raise ValueError('interrupted round requires recovery')
            if s['rounds']>=self.rounds:raise ValueError('campaign exhausted')
            r=s['rounds']+1;s['pending']=r;s['spent_steps']+=self.steps;s['attempts']+=self.batch;self.store.save(rev+1,s);rev+=1
            rng=random.Random((self.seed<<8)^r);audit=Audit(self.key,self.contract);records=[]
            for i in range(self.batch):
                parent=rng.choice(s['parents']);action=self.session.action(parent,rng);seed=rng.randrange(2**32);code=apply_patch(parent,propose(parent,action,seed));quality,stage=plasticity._assessment(code);base=plasticity._qualified(parent);ident=f'live-{r}-{i}'
                if quality is not None:
                    result=Cascade(42).evaluate(code);token=audit.issue(ident,code,result.metrics)
                    if not audit.verify(token,ident,code,result.metrics):raise RuntimeError('admission audit failed')
                    if _context(code) not in self.excluded and code not in s['parents']:s['parents'].append(code)
                row=trajectory(ident,0,'verified-parent',parent,code,action,quality is not None,quality if quality is not None else 0.,base,stage,seed);records.append(plasticity.validate_record(row))
            report=self.session.fit(tuple(records),self.validation,self.retention,steps=self.steps)
            s['active']=self.session.snapshot();s['history'].append({**report,'round':r,'records':len(records),'trajectories':records});s['rounds']=r;s['pending']=None;self.store.save(rev+1,s);return s['history'][-1]
    def recover(self,*,authorized=False):
        if authorized is not True:raise PermissionError('recovery authorization')
        with _lock(self.path):
            rev,s=self._load()
            if s['pending'] is not None:s['history'].append({'round':s['pending'],'interrupted':True});s['rounds']=s['pending'];s['pending']=None;self.store.save(rev+1,s)
            return s
    def rollback(self,*,authorized=False):
        if authorized is not True:raise PermissionError('rollback authorization')
        with _lock(self.path):
            rev,s=self._load()
            if s['pending'] is not None:raise ValueError('recover interrupted round first')
            s['active']=self.session.initial;s['rollbacks']+=1;self.session.restore(s['active']);self.store.save(rev+1,s);return s


def tiny_decoder(seed=42):
    """A small real causal attention decoder for dependency-independent test data."""
    import torch
    from torch import nn
    class Decoder(nn.Module):
        def __init__(self):
            super().__init__();d=24;self.embed=nn.Embedding(262,d);self.pos=nn.Embedding(MAX_TOKENS,d);self.q_proj=nn.Linear(d,d);self.k_proj=nn.Linear(d,d);self.v_proj=nn.Linear(d,d);self.out=nn.Linear(d,d);self.norm=nn.LayerNorm(d);self.head=nn.Linear(d,262)
        def forward(self,input_ids,attention_mask,use_cache=False):
            t=input_ids.shape[1];x=self.embed(input_ids)+self.pos(torch.arange(t,device=input_ids.device));q=self.q_proj(x);k=self.k_proj(x);v=self.v_proj(x);z=q@k.transpose(-1,-2)/math.sqrt(q.shape[-1]);mask=torch.ones(t,t,device=x.device,dtype=torch.bool).tril()[None] & attention_mask[:,None,:].bool();z=z.masked_fill(~mask,float('-inf'));a=torch.softmax(z,dim=-1)@v
            return SimpleNamespace(logits=self.head(self.norm(x+self.out(a))))
    with torch.random.fork_rng(devices=[]):torch.manual_seed(seed);model=Decoder()
    return Session(model,lambda code:[6+b for b in code.encode('ascii')],tuple(range(6)),encoder_id='0'*64,device='cpu',rank=2,seed=seed)


def demo(path):
    import torch
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    _,v,r,test=plasticity.fixture(42,groups=4);session=tiny_decoder();key=b'\x9a'*32  # synthetic local test fixture only
    campaign=OnlineCampaign(path,key,session,v[:12],r[:12],rounds=2,batch=4,steps=4,create=True);campaign.step(authorized=True)
    # Simulate process restart by reconstructing the entire model and ledger.
    other=tiny_decoder();campaign=OnlineCampaign(path,key,other,v[:12],r[:12],rounds=2,batch=4,steps=4);campaign.step(authorized=True);s=campaign.inspect();test_mse=other.evaluate(test[:12]);third=tiny_decoder();base_mse=third.evaluate(test[:12]);reloaded=OnlineCampaign(path,key,third,v[:12],r[:12],rounds=2,batch=4,steps=4).inspect();same=third.snapshot()==s['active']==reloaded['active'] and third.evaluate(test[:12])==test_mse
    return {'rounds':s['rounds'],'spent_steps':s['spent_steps'],'attempts':s['attempts'],'base_unchanged':other.base_digest()==other.base_sha,'trainable_parameters':other.trainable,'frozen_parameters':other.frozen,'replay_verified':same,'history':[{k:v for k,v in row.items() if k!='trajectories'} for row in s['history']],'test_mse':test_mse,'base_test_mse':base_mse,'backend':'tiny-decoder-cpu'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--demo',action='store_true');p.add_argument('--db',type=Path,required=True);p.add_argument('--model',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--splits',type=Path);p.add_argument('--device',choices=('cpu','cuda'),default='cuda');p.add_argument('--backend',choices=('transformers','native-llama'),default='transformers');p.add_argument('--rounds',type=int,default=4);p.add_argument('--batch',type=int,default=4);p.add_argument('--steps',type=int,default=8);p.add_argument('--create',action='store_true');p.add_argument('--authorize-training',action='store_true');p.add_argument('--recover',action='store_true');p.add_argument('--rollback',action='store_true');a=p.parse_args()
    if a.demo:
        print(json.dumps(demo(a.db),indent=2,allow_nan=False));return
    if not a.model or not a.key_file or not a.splits or not a.authorize_training:p.error('local model, key, verified splits and explicit authorization required')
    with a.key_file.open('rb') as f:key=f.read(4097)
    if not 32<=len(key)<=4096:raise ValueError('key size')
    with a.splits.open('rb') as f:raw=f.read(1048577)
    if len(raw)>1048576:raise ValueError('split cap')
    data=json.loads(raw);session=load_local(a.model,device=a.device,backend=a.backend);c=OnlineCampaign(a.db,key,session,tuple(data['validation']),tuple(data['retention']),rounds=a.rounds,batch=a.batch,steps=a.steps,create=a.create)
    if a.recover:out=c.recover(authorized=True)
    elif a.rollback:out=c.rollback(authorized=True)
    else:out=c.step(authorized=True)
    print(json.dumps({k:v for k,v in out.items() if k!='active'},indent=2,allow_nan=False))
if __name__=='__main__':main()
