"""Strict local CPU loader for the Llama-1/2-style untied decoder subset.

Standard separate q/k/v/o projections, grouped-query attention, unscaled RoPE,
RMSNorm and SwiGLU; exact Safetensors admission. No remote code, network,
quantized formats, tied embeddings, alternate RoPE or hidden fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import math

import torch
from torch import nn
from torch.nn import functional as F

MAX_CONTEXT = 512
MAX_PARAMETERS = 4_000_000_000
MAX_FORWARD_ELEMENTS = 64_000_000
MAX_TOKENIZER_BYTES = 16 * 1024 * 1024
FLOAT_DTYPES = {'F32', 'F16', 'BF16'}
PROMPT = 'Select one mutation operator (0-5) for expression: {}\nOperator: '


def _duplicates(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate model configuration key')
        out[key] = value
    return out


def _read(path, limit):
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular local model file required')
    with path.open('rb') as stream:
        raw = stream.read(limit+1)
    if not 0 < len(raw) <= limit:
        raise ValueError('local model file size')
    return raw


@dataclass(frozen=True)
class Config:
    vocab_size: int
    hidden_size: int
    intermediate_size: int
    num_hidden_layers: int
    num_attention_heads: int
    num_key_value_heads: int
    max_position_embeddings: int
    rms_norm_eps: float = 1e-6
    rope_theta: float = 10000.
    bos_token_id: int | None = None

    def __post_init__(self):
        caps = {'vocab_size':(6,262144),'hidden_size':(8,8192),
                'intermediate_size':(8,32768),'num_hidden_layers':(1,80),
                'num_attention_heads':(1,64),'num_key_value_heads':(1,64),
                'max_position_embeddings':(2,131072)}
        for key,(low,high) in caps.items():
            v=getattr(self,key)
            if type(v) is not int or not low<=v<=high:
                raise ValueError('native Llama config bound: '+key)
        if self.hidden_size % self.num_attention_heads or self.num_attention_heads % self.num_key_value_heads or self.head_dim%2:
            raise ValueError('native Llama head layout')
        if type(self.rms_norm_eps) not in (int,float) or not 1e-12<=self.rms_norm_eps<=.1:
            raise ValueError('native RMS epsilon')
        if type(self.rope_theta) not in (int,float) or not 1<=self.rope_theta<=1e9:
            raise ValueError('native RoPE base')
        if self.bos_token_id is not None and (type(self.bos_token_id) is not int or not 0<=self.bos_token_id<self.vocab_size):
            raise ValueError('native BOS id')
        if not 1<=self.parameter_count<=MAX_PARAMETERS:
            raise ValueError('native Llama parameter cap')

    @property
    def head_dim(self):
        return self.hidden_size//self.num_attention_heads

    @property
    def parameter_count(self):
        h=self.hidden_size;kv=self.num_key_value_heads*self.head_dim
        return 2*self.vocab_size*h+h+self.num_hidden_layers*(2*h*h+2*h*kv+3*h*self.intermediate_size+2*h)

    @classmethod
    def from_dict(cls, raw):
        fields={'vocab_size','hidden_size','intermediate_size','num_hidden_layers','num_attention_heads',
                'num_key_value_heads','max_position_embeddings','rms_norm_eps','rope_theta','bos_token_id'}
        inert={'model_type','architectures','hidden_act','tie_word_embeddings','attention_bias','mlp_bias',
               'rope_scaling','head_dim','pretraining_tp','attention_dropout','use_cache','torch_dtype','dtype',
               'initializer_range','transformers_version','_name_or_path','eos_token_id','pad_token_id'}
        if type(raw) is not dict or set(raw)-fields-inert or raw.get('model_type')!='llama':
            raise ValueError('unsupported native Llama config')
        if raw.get('architectures',['LlamaForCausalLM'])!=['LlamaForCausalLM'] or raw.get('hidden_act','silu')!='silu':
            raise ValueError('unsupported native Llama architecture')
        for flag in ('tie_word_embeddings','attention_bias','mlp_bias'):
            if raw.get(flag,False) is not False:
                raise ValueError('unsupported native Llama option: '+flag)
        if raw.get('rope_scaling') is not None or type(raw.get('pretraining_tp',1)) is not int or raw.get('pretraining_tp',1)!=1 or type(raw.get('attention_dropout',0)) not in (int,float) or raw.get('attention_dropout',0)!=0:
            raise ValueError('unsupported native Llama scaling/dropout')
        required=fields-{'num_key_value_heads','rms_norm_eps','rope_theta','bos_token_id'}
        if not required<=raw.keys():
            raise ValueError('missing native Llama config fields')
        args={k:raw[k] for k in fields if k in raw}
        args.setdefault('num_key_value_heads',args['num_attention_heads'])
        result=cls(**args)
        if 'head_dim' in raw and (type(raw['head_dim']) is not int or raw['head_dim']!=result.head_dim):
            raise ValueError('unsupported native Llama head dimension')
        return result


class RMSNorm(nn.Module):
    def __init__(self, hidden, eps):
        super().__init__()
        self.weight=nn.Parameter(torch.ones(hidden))
        self.eps=eps

    def forward(self,x):
        f=x.float()
        return self.weight*(f*torch.rsqrt(f.square().mean(-1,keepdim=True)+self.eps)).to(x.dtype)


class Attention(nn.Module):
    def __init__(self,cfg):
        super().__init__();h=cfg.hidden_size
        self.cfg=cfg;self.q_proj=nn.Linear(h,h,bias=False)
        kv=cfg.num_key_value_heads*cfg.head_dim
        self.k_proj=nn.Linear(h,kv,bias=False);self.v_proj=nn.Linear(h,kv,bias=False)
        self.o_proj=nn.Linear(h,h,bias=False)

    def forward(self,x,mask):
        b,t,_=x.shape;c=self.cfg;d=c.head_dim
        q=self.q_proj(x).reshape(b,t,c.num_attention_heads,d).transpose(1,2)
        k=self.k_proj(x).reshape(b,t,c.num_key_value_heads,d).transpose(1,2)
        v=self.v_proj(x).reshape(b,t,c.num_key_value_heads,d).transpose(1,2)
        positions=torch.arange(t,device=x.device,dtype=torch.float32)
        frequency=c.rope_theta**(-torch.arange(0,d,2,device=x.device,dtype=torch.float32)/d)
        angle=positions[:,None]*frequency[None,:]
        cos=torch.cat((angle.cos(),angle.cos()),-1)[None,None,:,:]
        sin=torch.cat((angle.sin(),angle.sin()),-1)[None,None,:,:]
        def rotate(tensor):
            a,b=tensor.chunk(2,dim=-1)
            return tensor*cos+torch.cat((-b,a),dim=-1)*sin
        q,k=rotate(q),rotate(k)
        repeat=c.num_attention_heads//c.num_key_value_heads
        k=k.repeat_interleave(repeat,dim=1);v=v.repeat_interleave(repeat,dim=1)
        # Explicit right-padding and causal keys. A valid first token is
        # enforced by CausalLM, so no query has an all-masked softmax row.
        allowed=torch.ones((t,t),device=x.device,dtype=torch.bool).tril()[None,None,:,:] & mask[:,None,None,:].bool()
        attended=F.scaled_dot_product_attention(q,k,v,attn_mask=allowed,dropout_p=0.)
        return self.o_proj(attended.transpose(1,2).reshape(b,t,-1))


class MLP(nn.Module):
    def __init__(self,c):
        super().__init__();h,i=c.hidden_size,c.intermediate_size
        self.gate_proj=nn.Linear(h,i,bias=False);self.up_proj=nn.Linear(h,i,bias=False)
        self.down_proj=nn.Linear(i,h,bias=False)

    def forward(self,x):
        return self.down_proj(F.silu(self.gate_proj(x))*self.up_proj(x))


class Block(nn.Module):
    def __init__(self,c):
        super().__init__()
        self.input_layernorm=RMSNorm(c.hidden_size,c.rms_norm_eps)
        self.self_attn=Attention(c)
        self.post_attention_layernorm=RMSNorm(c.hidden_size,c.rms_norm_eps)
        self.mlp=MLP(c)

    def forward(self,x,mask):
        x=x+self.self_attn(self.input_layernorm(x),mask)
        return x+self.mlp(self.post_attention_layernorm(x))


class Decoder(nn.Module):
    def __init__(self,c):
        super().__init__()
        self.embed_tokens=nn.Embedding(c.vocab_size,c.hidden_size)
        self.layers=nn.ModuleList(Block(c) for _ in range(c.num_hidden_layers))
        self.norm=RMSNorm(c.hidden_size,c.rms_norm_eps)

    def forward(self,ids,mask):
        x=self.embed_tokens(ids)
        for layer in self.layers:x=layer(x,mask)
        return self.norm(x)


class CausalLM(nn.Module):
    def __init__(self,cfg):
        super().__init__()
        if type(cfg) is not Config:raise ValueError('native Llama config type')
        self.cfg=cfg;self.model=Decoder(cfg);self.lm_head=nn.Linear(cfg.hidden_size,cfg.vocab_size,bias=False)

    def forward(self,input_ids,attention_mask,use_cache=False):
        ids,mask=input_ids,attention_mask
        if use_cache is not False or ids.ndim!=2 or mask.shape!=ids.shape or ids.dtype!=torch.long or ids.device.type!='cpu' or mask.device!=ids.device:
            raise ValueError('native causal input contract')
        if not 1<=ids.shape[0]<=64 or not 1<=ids.shape[1]<=min(MAX_CONTEXT,self.cfg.max_position_embeddings):
            raise ValueError('native causal input bounds')
        b,t=ids.shape
        c=self.cfg
        # Coarse safety envelope for the largest logits, attention and retained
        # training activations. It is not a hardware memory guarantee.
        if max(b*t*c.vocab_size,b*c.num_attention_heads*t*t,b*t*(c.hidden_size+c.intermediate_size)*c.num_hidden_layers)>MAX_FORWARD_ELEMENTS:
            raise ValueError('native forward work envelope')
        if bool((ids<0).any()) or bool((ids>=self.cfg.vocab_size).any()) or bool(((mask!=0)&(mask!=1)).any()) or not bool(mask[:,0].all()) or bool((mask[:,1:]>mask[:,:-1]).any()):
            raise ValueError('native token or right-padding contract')
        return SimpleNamespace(logits=self.lm_head(self.model(ids,mask)))


def _encoder(raw,cfg):
    import sentencepiece as sp
    tok=sp.SentencePieceProcessor(model_proto=raw)
    if tok.vocab_size()!=cfg.vocab_size or cfg.bos_token_id is not None and tok.bos_id()!=cfg.bos_token_id:
        raise ValueError('native tokenizer vocabulary/BOS mismatch')
    bos=[tok.bos_id()] if tok.bos_id()>=0 else []
    def rows(code):return [tok.encode(PROMPT.format(code)+str(i),out_type=int) for i in range(6)]
    sample=rows('-(x+y)')
    if any(len(r)<2 for r in sample):raise ValueError('native operator tokenization')
    actions=tuple(r[-1] for r in sample)
    if len(set(actions))!=6 or any(r[:-1]!=sample[0][:-1] for r in sample) or any(j in (tok.unk_id(),tok.bos_id(),tok.eos_id(),tok.pad_id()) for j in actions):
        raise ValueError('native operator token contract')
    def encode(code):
        variants=rows(code);prefix=variants[0][:-1]
        if any(r!=prefix+[a] for r,a in zip(variants,actions)):
            raise ValueError('native context-dependent operator tokens')
        out=bos+prefix
        if not 1<=len(out)<=min(MAX_CONTEXT,cfg.max_position_embeddings):raise ValueError('native context cap')
        return out
    return encode,actions


def _load_session(path,manifest,*,device,rank,seed):
    """Admit all exact tensor keys and shapes before allocating model weights."""
    from safetensors import safe_open
    from .llm_plasticity import Session, model_manifest, memory_admission
    if device!='cpu':raise ValueError('native Llama backend is CPU-only')
    path=Path(path).resolve(strict=True)
    if type(manifest) is not dict or set(manifest)!={'parameter_elements','storage_bytes','config_sha256','files'} or type(manifest['files']) is not list or not 1<=len(manifest['files'])<=128:
        raise ValueError('native manifest contract')
    names=[]
    for item in manifest['files']:
        if type(item) is not dict or set(item)!={'name','bytes','sha256'}:
            raise ValueError('native shard manifest')
        name=item['name']
        if type(name) is not str or Path(name).name!=name or '\\' in name or not name.endswith('.safetensors'):
            raise ValueError('unsafe native shard name')
        names.append(name)
    if len(set(names))!=len(names):raise ValueError('duplicate native shard names')
    config_raw=_read(path/'config.json',1_048_576)
    if hashlib.sha256(config_raw).hexdigest()!=manifest['config_sha256']:raise ValueError('configuration changed during admission')
    cfg=Config.from_dict(json.loads(config_raw,object_pairs_hook=_duplicates))
    if cfg.parameter_count!=manifest['parameter_elements']:raise ValueError('native Llama exact parameter count')
    memory_admission(manifest,device='cpu')
    tokenizer_raw=_read(path/'tokenizer.model',MAX_TOKENIZER_BYTES)
    encoder,actions=_encoder(tokenizer_raw,cfg)
    # Meta construction avoids allocating randomly initialized model weights.
    with torch.device('meta'):model=CausalLM(cfg)
    expected={k:tuple(v.shape) for k,v in model.state_dict().items()}
    if sum(math.prod(s) for s in expected.values())!=cfg.parameter_count:raise RuntimeError('native parameter invariant')
    seen=set()
    for item in manifest['files']:
        f=path/item['name']
        if f.is_symlink() or not f.is_file():raise ValueError('unsafe native tensor file')
        with safe_open(str(f),framework='pt',device='cpu') as handle:
            for k in handle.keys():
                sl=handle.get_slice(k)
                if k in seen or k not in expected or tuple(sl.get_shape())!=expected[k] or sl.get_dtype() not in FLOAT_DTYPES:
                    raise ValueError('unexpected native tensor key, shape or dtype')
                seen.add(k)
    if seen!=expected.keys():raise ValueError('missing native tensor keys')
    state={}
    for item in manifest['files']:
        f=path/item['name']
        if f.is_symlink() or not f.is_file():raise ValueError('unsafe native tensor file')
        with safe_open(str(f),framework='pt',device='cpu') as handle:
            for k in handle.keys():
                if k in state or k not in expected:raise ValueError('native tensors changed during load')
                value=handle.get_tensor(k)
                if tuple(value.shape)!=expected[k] or value.dtype not in (torch.float16,torch.bfloat16,torch.float32):raise ValueError('native tensor changed during load')
                value=value.to(dtype=torch.float32,copy=True).contiguous()
                flat=value.view(-1)
                for start in range(0,flat.numel(),1_000_000):
                    if not bool(torch.isfinite(flat[start:start+1_000_000]).all()):raise ValueError('nonfinite native tensor')
                state[k]=value
    # No partial or random-weight load; retained weights are private copies.
    model.load_state_dict(state,strict=True,assign=True)
    if model_manifest(path)!=manifest or _read(path/'tokenizer.model',MAX_TOKENIZER_BYTES)!=tokenizer_raw:
        raise ValueError('local model changed during load')
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    tokenizer_hash=hashlib.sha256(tokenizer_raw).hexdigest()
    from .graph_memory import canonical
    encoder_id=hashlib.sha256(canonical(['native-llama-v1',source_hash,tokenizer_hash,manifest['config_sha256'],actions,PROMPT]).encode()).hexdigest()
    session=Session(model,encoder,actions,encoder_id=encoder_id,device='cpu',rank=rank,seed=seed)
    session.microbatch=1
    session.local_manifest={**manifest,'backend':'native-llama','tokenizer_sha256':tokenizer_hash,'backend_source_sha256':source_hash}
    return session
