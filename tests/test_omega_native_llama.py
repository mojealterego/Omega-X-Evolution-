"""v34: actual native Llama-format weights, causal inference and LoRA."""
import json
from pathlib import Path
import pytest
import torch
import sentencepiece as sp
from safetensors.torch import save_file
from omega_x_evolution import llm_plasticity, plasticity


def fixture(path, *, hidden=48, layers=2, pretrain=False):
    from omega_x_evolution.native_llama import Config, CausalLM
    path.mkdir()
    corpus=path/'corpus.txt'
    corpus.write_text('\n'.join(['Select one mutation operator (0-5) for expression: -(x+y)\nOperator: '+str(i) for i in range(6)]*20))
    sp.SentencePieceTrainer.train(input=str(corpus),model_prefix=str(path/'tokenizer'),vocab_size=128,model_type='bpe',hard_vocab_limit=False, minloglevel=2,num_threads=1,shuffle_input_sentence=False)
    tok=sp.SentencePieceProcessor(model_file=str(path/'tokenizer.model'))
    cfg={'model_type':'llama','architectures':['LlamaForCausalLM'],'hidden_size':hidden,'intermediate_size':2*hidden,'num_hidden_layers':layers,'num_attention_heads':4,'num_key_value_heads':2,'max_position_embeddings':512,'vocab_size':tok.vocab_size(),'hidden_act':'silu','tie_word_embeddings':False,'rms_norm_eps':1e-5,'rope_theta':10000.,'bos_token_id':tok.bos_id()}
    (path/'config.json').write_text(json.dumps(cfg))
    config=Config.from_dict(cfg)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(42);model=CausalLM(config)
        if pretrain:
            batch=torch.randint(0,config.vocab_size,(2,18));mask=torch.ones_like(batch)
            opt=torch.optim.AdamW(model.parameters(),lr=.002)
            loss=[]
            for _ in range(3):
                opt.zero_grad(set_to_none=True);logits=model(batch,mask).logits
                value=torch.nn.functional.cross_entropy(logits[:,:-1].reshape(-1,config.vocab_size),batch[:,1:].reshape(-1));value.backward();opt.step();loss.append(float(value.detach()))
            assert loss[-1]<loss[0]
    tensors={k:t.detach().contiguous() for k,t in model.state_dict().items()}
    save_file(tensors,str(path/'model.safetensors'))
    return model,cfg,tensors


def test_v34_real_native_loader_logits_and_causality(tmp_path):
    torch.set_num_threads(1)
    model,cfg,tensors=fixture(tmp_path/'model')
    session=llm_plasticity.load_local(tmp_path/'model',device='cpu',backend='native-llama')
    assert session.local_manifest['backend']=='native-llama'
    tokens=torch.tensor([[1,5,7,9],[1,5,8,11]])
    mask=torch.ones_like(tokens)
    with torch.no_grad():
        expected=model(tokens,mask).logits;actual=session.model(tokens,mask).logits
        torch.testing.assert_close(actual,expected,rtol=0,atol=0)
        torch.testing.assert_close(actual[0,:2],actual[1,:2],rtol=0,atol=1e-6)
    assert session.frozen==sum(t.numel() for t in tensors.values())
    assert session.trainable==sum(p.numel() for p in session.params.values())>0
    assert len(set(session.action_ids))==6
    assert session.base_digest()==session.base_sha


def test_v34_actual_pretraining_checkpoint_and_lora(tmp_path):
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    model,cfg,tensors=fixture(tmp_path/'model',hidden=192,layers=3,pretrain=True)
    assert sum(t.numel() for t in tensors.values())>1_000_000
    path=tmp_path/'model';(path/'model.safetensors').unlink()
    ks=sorted(tensors);mapping={}
    for i,keys in enumerate((ks[::2],ks[1::2]),1):
        name=f'model-{i:05d}-of-00002.safetensors';save_file({k:tensors[k] for k in keys},str(path/name));mapping.update({k:name for k in keys})
    (path/'model.safetensors.index.json').write_text(json.dumps({'weight_map':mapping}))
    session=llm_plasticity.load_local(path,device='cpu',backend='native-llama',rank=2)
    before=session.snapshot();base=session.base_sha
    train,val,ret,test=plasticity.fixture(42,groups=4)
    report=session.fit(train[:4],val[:4],ret[:4],steps=2)
    assert report['actual_steps']==2 and report['candidate_sha256']!=llm_plasticity._digest(before)
    assert session.base_digest()==base
    if not report['promoted']:assert session.snapshot()==before
    other=llm_plasticity.load_local(path,device='cpu',backend='native-llama',rank=2)
    other.restore(session.snapshot());assert other.base_sha==base and other.encoder_id==session.encoder_id
    assert other.evaluate(test[:4])==session.evaluate(test[:4])


@pytest.mark.parametrize('defect',['missing','extra','shape','dtype','nan','unsupported','tokenizer-link'])
def test_v34_reject_incomplete_or_incompatible_artifacts(tmp_path,defect):
    torch.set_num_threads(1)
    path=tmp_path/'model';_,cfg,tensors=fixture(path)
    key='model.layers.0.self_attn.q_proj.weight'
    if defect=='missing': tensors.pop(key)
    elif defect=='extra': tensors['unrecognized']=torch.ones(1)
    elif defect=='shape': tensors[key]=tensors[key][:-1].contiguous()
    elif defect=='dtype': tensors[key]=tensors[key].to(torch.int32)
    elif defect=='nan': tensors[key]=tensors[key].clone();tensors[key][0,0]=float('nan')
    elif defect=='unsupported': cfg['rope_scaling']={'type':'linear','factor':2};(path/'config.json').write_text(json.dumps(cfg))
    elif defect=='tokenizer-link': (path/'tokenizer.model').rename(tmp_path/'other.model');(path/'tokenizer.model').symlink_to(tmp_path/'other.model')
    save_file(tensors,str(path/'model.safetensors'))
    with pytest.raises((ValueError,RuntimeError)):
        llm_plasticity.load_local(path,device='cpu',backend='native-llama')


def test_v34_independent_float64_gqa_rope_reference(tmp_path):
    """Compare a direct per-head scalar-position oracle, not model self-replay."""
    import math
    torch.set_num_threads(1)
    _,cfg,tensors=fixture(tmp_path/'model')
    session=llm_plasticity.load_local(tmp_path/'model',device='cpu',backend='native-llama')
    ids=torch.tensor([[1,5,7,9]])
    # Independent float64 reference on raw checkpoint tensors.
    w={k:v.double() for k,v in tensors.items()}
    h=cfg['hidden_size'];nh=cfg['num_attention_heads'];nk=cfg['num_key_value_heads'];d=h//nh
    eps=cfg['rms_norm_eps'];theta=cfg['rope_theta'];t=ids.size(1)
    def norm(x,weight):return x/(x.square().sum(-1,keepdim=True)/h+eps).sqrt()*weight
    def linear(x,key):return x @ w[key].T
    def rotated(x,position):
        y=x.clone()
        for j in range(d//2):
            angle=position/(theta**(2*j/d));c,s=math.cos(angle),math.sin(angle)
            y[j]=x[j]*c-x[j+d//2]*s;y[j+d//2]=x[j+d//2]*c+x[j]*s
        return y
    x=w['model.embed_tokens.weight'][ids[0]]
    for layer in range(cfg['num_hidden_layers']):
        prefix=f'model.layers.{layer}.'
        z=norm(x,w[prefix+'input_layernorm.weight']);a=prefix+'self_attn.'
        q=linear(z,a+'q_proj.weight').reshape(t,nh,d)
        k=linear(z,a+'k_proj.weight').reshape(t,nk,d)
        v=linear(z,a+'v_proj.weight').reshape(t,nk,d)
        outputs=[]
        for pos in range(t):
            heads=[]
            for head in range(nh):
                kv=head//(nh//nk);query=rotated(q[pos,head],pos)
                logits=torch.stack([(query*rotated(k[j,kv],j)).sum()/math.sqrt(d) for j in range(pos+1)])
                probs=logits.softmax(0)
                heads.append(sum(probs[j]*v[j,kv] for j in range(pos+1)))
            outputs.append(torch.cat(heads))
        x=x+linear(torch.stack(outputs),a+'o_proj.weight');z=norm(x,w[prefix+'post_attention_layernorm.weight'])
        g=linear(z,prefix+'mlp.gate_proj.weight');u=linear(z,prefix+'mlp.up_proj.weight')
        x=x+linear(g*g.sigmoid()*u,prefix+'mlp.down_proj.weight')
    expected=linear(norm(x,w['model.norm.weight']),'lm_head.weight')
    with torch.no_grad():
        actual=session.model(ids,torch.ones_like(ids)).logits[0].double()
        torch.testing.assert_close(actual,expected,rtol=1e-5,atol=2e-6)
        padded=torch.tensor([[1,5,7,9,10,11]]);mask=torch.tensor([[1,1,1,1,0,0]])
        torch.testing.assert_close(session.model(padded,mask).logits[0,:4].double(),actual,rtol=1e-5,atol=2e-6)
    with pytest.raises(ValueError):session.model(ids,torch.tensor([[1,0,1,0]]))


def test_v34_duplicate_json_and_no_random_fallback(tmp_path):
    path=tmp_path/'model';_,cfg,_=fixture(path)
    raw=json.dumps(cfg);(path/'config.json').write_text(raw[:-1]+',"hidden_size":48}')
    with pytest.raises(ValueError,match='duplicate model configuration key'):
        llm_plasticity.load_local(path,device='cpu',backend='native-llama')


def test_v34_native_campaign_restart_and_authorized_rollback(tmp_path):
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    path=tmp_path/'model';fixture(path)
    _,val,ret,test=plasticity.fixture(42,groups=4)
    def load():return llm_plasticity.load_local(path,device='cpu',backend='native-llama')
    session=load()
    db=tmp_path/'campaign.db';key=b'c'*32
    def open_campaign(s,create=False):return llm_plasticity.OnlineCampaign(db,key,s,val[:4],ret[:4],rounds=2,batch=2,steps=2,create=create)
    campaign=open_campaign(session,True)
    with pytest.raises(PermissionError):campaign.step()
    r=campaign.step(authorized=True);assert r['actual_steps']==2
    initial=session.initial;active=session.snapshot();base=session.base_sha
    other=load();resumed=open_campaign(other)
    assert other.snapshot()==active and other.base_sha==base
    assert resumed.step(authorized=True)['actual_steps']==2
    assert resumed.inspect()['spent_steps']==4
    with pytest.raises(PermissionError):resumed.rollback()
    assert resumed.rollback(authorized=True)['active']==initial
    assert other.base_digest()==base


def test_v34_native_bfloat16_exact_conversion_and_shard_path_guard(tmp_path):
    from omega_x_evolution.native_llama import _load_session
    torch.set_num_threads(1)
    path=tmp_path/'model';model,_,tensors=fixture(path)
    reduced={k:t.to(torch.bfloat16) for k,t in tensors.items()}
    save_file(reduced,str(path/'model.safetensors'))
    model.load_state_dict({k:v.float() for k,v in reduced.items()},strict=True)
    s=llm_plasticity.load_local(path,device='cpu',backend='native-llama')
    ids=torch.tensor([[1,5,8]])
    with torch.no_grad():torch.testing.assert_close(s.model(ids,torch.ones_like(ids)).logits,model(ids,torch.ones_like(ids)).logits,rtol=0,atol=0)
    info=llm_plasticity.model_manifest(path);info['files'][0]['name']='../model.safetensors'
    with pytest.raises(ValueError,match='unsafe native shard name'):
        _load_session(path,info,device='cpu',rank=2,seed=42)
