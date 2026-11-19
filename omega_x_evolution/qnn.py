"""Optional Qualcomm HTP ONNX Runtime adapter; no automatic CPU EP fallback.

The operator supplies a compatible installed QNN runtime and SDK. Only a
static graph generated from an existing validated MLP can enter the provider.
"""
from __future__ import annotations
import numpy as np
from .compute import Device, DEFAULT_CAP, ComputeError
from .neural import Model, _array


class QNNUnavailable(ComputeError):pass


def export_onnx(model:Model,samples:int):
    if not isinstance(model,Model) or type(samples) is not int or not 1<=samples<=512: raise ValueError('invalid ONNX model or shape')
    try:import onnx
    except ImportError as exc:raise QNNUnavailable('ONNX not installed') from exc
    h=onnx.helper; tensors=[];nodes=[];last='input'
    for i,(w,b) in enumerate(zip(model.weights,model.biases)):
        wn=f'w{i}';bn=f'b{i}'; mm=f'mm{i}'; add=f'add{i}'
        tensors.extend([onnx.numpy_helper.from_array(w.astype(np.float32),wn),onnx.numpy_helper.from_array(b.astype(np.float32),bn)])
        nodes.extend([h.make_node('MatMul',[last,wn],[mm]),h.make_node('Add',[mm,bn],[add])]);last=add
        if i<len(model.weights)-1:
            last=f'activation{i}';nodes.append(h.make_node('Tanh' if model.architecture.activation=='tanh' else 'Relu',[add],[last]))
    tensors.append(onnx.numpy_helper.from_array(np.asarray([model.scale],dtype=np.float32),'scale'))
    nodes.append(h.make_node('Mul',[last,'scale'],['output']))
    graph=h.make_graph(nodes,'omega_mlp',[h.make_tensor_value_info('input',onnx.TensorProto.FLOAT,[samples,2])],[h.make_tensor_value_info('output',onnx.TensorProto.FLOAT,[samples,1])],initializer=tensors)
    proto=h.make_model(graph,opset_imports=[h.make_opsetid('',13)],ir_version=8);onnx.checker.check_model(proto)
    return proto.SerializeToString()


class QNNBackend:
    device=Device('qnn:htp','npu',DEFAULT_CAP,True)

    def __init__(self):
        try:import onnxruntime as ort
        except (ImportError,OSError) as exc:raise QNNUnavailable('ONNX Runtime unavailable') from exc
        if 'QNNExecutionProvider' not in ort.get_available_providers(): raise QNNUnavailable('QNN EP unavailable')
        self._ort=ort

    def infer(self,model,rows):
        # QNN HTP uses a static shape and may refuse unsupported floating-point
        # operators. The router rejects numerical deviations; never enlarge its tolerance.
        x,_=_array(rows);ort=self._ort;opts=ort.SessionOptions();opts.add_session_config_entry('session.disable_cpu_ep_fallback','1')
        try:
            session=ort.InferenceSession(export_onnx(model,len(rows)),sess_options=opts,providers=['QNNExecutionProvider'],provider_options=[{'backend_type':'htp','enable_htp_fp16_precision':'1'}])
            session.disable_fallback()
            if session.get_providers()[0]!='QNNExecutionProvider':raise ComputeError('QNN provider not active')
            return np.asarray(session.run(['output'],{'input':x.astype(np.float32)})[0],dtype=np.float64)
        except QNNUnavailable:raise
        except Exception as exc:raise ComputeError('QNN graph rejected or execution failed') from exc
