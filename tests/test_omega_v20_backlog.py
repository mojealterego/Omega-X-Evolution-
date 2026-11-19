import json
import numpy as np
import pytest
from omega_x_evolution.graph_memory import GraphMemory, IntegrityError
from omega_x_evolution.semantic_memory import retrieve, grounded_quotes
from omega_x_evolution.training import Trainer
from omega_x_evolution.qnn import QNNBackend, QNNUnavailable
from omega_x_evolution.neural import BASELINE, fit, predict
from omega_x_evolution.neuro_symbolic import fixture
from omega_x_evolution.compute import CPUBackend, Router


def test_semantic_graph_and_grounded_output(tmp_path):
    m=GraphMemory(tmp_path/'graph.db',b'a'*32,'lab')
    a=m.add('hypothesis','oscillator harmonic displacement frequency',{})
    b=m.add('evidence','harmonic energy conservation',{'verified':True})
    m.link(a,'supports',b)
    other=GraphMemory(m.path,b'b'*32,'other');other.add('result','oscillator confidential',{})
    results=retrieve(m,'oscillator displacement',limit=4)
    assert a==results[0]['id'] and b in {r['id'] for r in results}
    q=grounded_quotes(results, [{'id':a,'quote':'harmonic displacement'}])
    assert q[0]['quote']=='harmonic displacement' and q[0]['id']==a
    with pytest.raises(ValueError): grounded_quotes(results,[{'id':a,'quote':'proved breakthrough'}])
    with pytest.raises(ValueError): grounded_quotes(results,[{'id':'0'*64,'quote':'oscillator'}])


def test_real_torch_training_and_replay():
    import importlib.util
    if importlib.util.find_spec('torch') is None: pytest.skip('optional Torch absent')
    d=fixture('smooth',seed=17)
    model=Trainer('cpu',timeout=60).fit(BASELINE,d.train,epochs=25,seed=19)
    ref=fit(BASELINE,d.train,epochs=25,seed=19)
    assert np.allclose(predict(model,d.validation),predict(ref,d.validation),rtol=1e-8,atol=1e-9)
    assert model.losses[-1]<model.losses[0]
    with pytest.raises(ValueError): Trainer('shell')


def test_qnn_missing_provider_fails_closed(monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(get_available_providers=lambda:['CPUExecutionProvider']))
    with pytest.raises(QNNUnavailable): QNNBackend()


def test_torch_training_work_cap_and_plan_roundtrip():
    from omega_x_evolution.experiments import design, NEURAL, RESIDUAL, Plan, execute
    d=fixture('smooth',seed=14); unit=len(d.train)*5
    assert design(d,epochs=5,work_cap=unit*NEURAL.parameters,training_backend='cpu').candidates==('symbolic',)
    p=design(d,epochs=5,work_cap=2*unit*NEURAL.parameters,training_backend='cpu')
    assert p.candidates==('symbolic','neural') and Plan.from_json(p.to_json())==p
    assert 'training_backend' not in design(d).to_json()
    import importlib.util
    if importlib.util.find_spec('torch') is None: pytest.skip('optional Torch absent')
    r=execute(p,d)
    assert r['training_work']==2*unit*NEURAL.parameters and r['training_backend']=='cpu'


def test_qnn_provider_contract_and_no_fallback(monkeypatch):
    from types import SimpleNamespace
    from omega_x_evolution import qnn
    import sys
    d=fixture('xor'); m=fit(BASELINE,d.train,epochs=2)
    seen={}
    class Options:
        def add_session_config_entry(self,k,v): seen[k]=v
    class Session:
        def __init__(self,blob,**kwargs): seen.update(kwargs); assert blob==b'onnx'
        def disable_fallback(self): seen['disable_fallback']=True
        def get_providers(self): return ['QNNExecutionProvider']
        def run(self,outputs,inputs): return [predict(m,d.test).astype(np.float32)]
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(get_available_providers=lambda:['QNNExecutionProvider'],SessionOptions=Options,InferenceSession=Session))
    monkeypatch.setattr(qnn,'export_onnx',lambda model,n:b'onnx')
    backend=qnn.QNNBackend()
    # Explicitly mark the test double as simulated; never call this hardware evidence.
    from omega_x_evolution.compute import Device
    backend.device=Device('qnn:sim','npu',1024*1024,False)
    r=Router([backend],memory_cap=1024*1024).infer(m,d.test,prefer=('npu',))
    assert not r.physical and seen['session.disable_cpu_ep_fallback']=='1' and seen['disable_fallback']
    assert seen['provider_options']==[{'backend_type':'htp','enable_htp_fp16_precision':'1'}]
    monkeypatch.setattr(Session,'get_providers',lambda self:['CPUExecutionProvider'])
    with pytest.raises(Exception,match='no verified device'): Router([backend]).infer(m,d.test,prefer=('npu',))


def test_local_llm_http_quote_contract(tmp_path):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from omega_x_evolution.semantic_memory import LocalSelector
    m=GraphMemory(tmp_path/'g.db',b'm'*32,'lab'); i=m.add('evidence','verified oscillator model',{})
    records=retrieve(m,'oscillator'); bad=[False]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path=='/v1/chat/completions'
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert 'tools' not in payload
            response={'choices':[{'message':{'content':json.dumps([{'id':i,'quote':'fabricated' if bad[0] else 'oscillator model'}])}}]}
            raw=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def log_message(self,*args): pass
    with HTTPServer(('127.0.0.1',0),Handler) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            selector=LocalSelector(server.server_port,'test-double')
            assert selector.select('oscillator',records)[0]['quote']=='oscillator model'
            bad[0]=True
            with pytest.raises(ValueError): selector.select('oscillator',records)
        finally: server.shutdown();thread.join(timeout=3)
