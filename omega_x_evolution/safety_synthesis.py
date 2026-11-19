"""Candidate-specific safety obligations under immutable binary64 interpreter policy.

Interval proof certificates cover all binary64 input pairs in [0,1]^2.
Conservative outward rounding can yield unknown; unknown never grants admission.
Candidate-specific specifications and finite CTL proof certificates.
"""
from __future__ import annotations
import argparse
import ast
from functools import lru_cache
import hashlib
import json
import math
from .engine import Expression

LIMIT = 1e12
MAX_DEPTH = 8
POLICY = 'omega-binary64-totality-v2'


def _wire(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_wire(value).encode()).hexdigest()


def _out(values):
    if not all(math.isfinite(v) for v in values):
        raise ArithmeticError('nonfinite interval')
    return math.nextafter(min(values), -math.inf), math.nextafter(max(values), math.inf)


def _interval(node, box, obligations, path='root'):
    if isinstance(node, ast.Constant):
        v=float(node.value); bounds=(v,v)
    elif isinstance(node, ast.Name):
        bounds=box[0 if node.id=='x' else 1]
    elif isinstance(node, ast.UnaryOp):
        a=_interval(node.operand,box,obligations,path+'.0')
        bounds=(-a[1],-a[0]) if isinstance(node.op,ast.USub) else a
    elif isinstance(node, ast.BinOp):
        a=_interval(node.left,box,obligations,path+'.0'); b=_interval(node.right,box,obligations,path+'.1')
        if isinstance(node.op,ast.Add): bounds=_out((a[0]+b[0],a[1]+b[1]))
        elif isinstance(node.op,ast.Sub): bounds=_out((a[0]-b[1],a[1]-b[0]))
        elif isinstance(node.op,ast.Mult): bounds=_out(tuple(x*y for x in a for y in b))
        elif isinstance(node.op,ast.Div):
            if b[0]<=0<=b[1]: raise ArithmeticError('denominator may contain zero')
            obligations.append([path,'nonzero',list(b)])
            bounds=_out(tuple(x/y for x in a for y in b))
        else: raise ArithmeticError('unsupported operation')
    elif isinstance(node,ast.Call):
        args=[_interval(n,box,obligations,path+f'.{i}') for i,n in enumerate(node.args)]
        a=args[0]
        if node.func.id=='abs': bounds=(0. if a[0]<=0<=a[1] else min(map(abs,a)),max(map(abs,a)))
        elif node.func.id=='min': bounds=(min(a[0],args[1][0]),min(a[1],args[1][1]))
        elif node.func.id=='max': bounds=(max(a[0],args[1][0]),max(a[1],args[1][1]))
        else: raise ArithmeticError('unsupported call')
    else: raise ArithmeticError('unsupported node')
    if not all(math.isfinite(v) and abs(v)<=LIMIT for v in bounds):
        raise ArithmeticError('intermediate bound unproved')
    obligations.append([path,'finite_bound',list(bounds)])
    return bounds


def specification(expr):
    """Generate typed executable verification obligations from the validated AST."""
    nodes=[]; obligations=[]; sources={}
    def visit(node,path):
        if isinstance(node,ast.BinOp):children=(node.left,node.right);op=type(node.op).__name__
        elif isinstance(node,ast.UnaryOp):children=(node.operand,);op=type(node.op).__name__
        elif isinstance(node,ast.Call):children=tuple(node.args);op=node.func.id
        elif isinstance(node,ast.Name):children=();op=node.id
        else:children=();op='literal'
        record={'path':path,'operator':op,'children':[path+f'.{i}' for i in range(len(children))]}
        if isinstance(node,ast.Constant):record['value']=float(node.value)
        nodes.append(record);sources[path]=ast.unparse(node)
        for i,child in enumerate(children):visit(child,path+f'.{i}')
        obligations.append({'path':path,'kind':'finite_bound','limit':LIMIT})
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Div):obligations.append({'path':path,'kind':'nonzero','operand':path+'.1'})
    visit(expr.tree,'root')
    return {'domain':[[0.,1.],[0.,1.]],'semantics':'CPython binary64 round-to-nearest','nodes':nodes,'obligations':obligations},sources


def modal_certificate(obligations, *, bypass=False):
    from .modal import Model,check,prove_k
    # Every checked obligation is a guard on evaluation; each failure is terminal.
    labels={};edges=[];facts=[]
    for i,(path,kind) in enumerate(obligations):
        state=f'proof{i}';next_state=f'proof{i+1}' if i+1<len(obligations) else 'evaluate'
        edges.append((state,(next_state,'reject')))
        labels[state]=tuple(facts);facts.append(f'{kind}:{path}')
    facts.append('proof')
    for current,nxt,flag in (('evaluate','performance','empirical'),('performance','audit','performance'),('audit','admitted','audit')):
        labels[current]=tuple(facts+( ['evaluating'] if current=='evaluate' else []));edges.append((current,(nxt,'reject')));facts.append(flag)
    edges.extend((('admitted',('admitted',)),('reject',('reject',))))
    labels['admitted']=tuple(facts+['admitted']);labels['reject']=('rejected',)
    if bypass:
        edges[0]=(edges[0][0],(edges[0][1][0],'reject','bad'))
        edges.append(('bad',('bad',)));labels['bad']=('admitted','evaluating')
    def conjunction(xs):
        if len(xs)==1:return ('atom',xs[0])
        mid=len(xs)//2;return ('and',conjunction(xs[:mid]),conjunction(xs[mid:]))
    formula=('and',('AG',('implies',('atom','admitted'),conjunction(facts))),
        ('AG',('implies',('atom','evaluating'),conjunction(facts[:-3]))))
    ctl=check(Model(tuple(edges),labels),formula,edges[0][0])
    # The logical deduction used to propagate candidate-specific guards is also
    # proved in K, independently of the finite transition graph. Premises remain
    # concrete model/evaluator obligations; logical validity alone is not safety.
    checked=conjunction(facts[:-4])
    admitted=('atom','admitted');proof=('atom','proof')
    theorem=('implies',('and',('box',('implies',admitted,proof)),('box',('implies',proof,checked))),('box',('implies',admitted,checked)))
    logical=prove_k(theorem)
    return {**ctl,'holds':ctl['holds'] and logical['proved'],'formula':formula,'k_formula':theorem,'k_proof':logical}

def modal_invariant(*,bypass=False):
    return modal_certificate([('root','finite_bound')],bypass=bypass)['holds']


@lru_cache(maxsize=512)
def _prove(code):
    digest=hashlib.sha256(code.encode()).hexdigest()
    outcome={'policy':POLICY,'source_sha256':digest,'proved':False,'boxes':0,'obligations':0,'digest':'','reason':'unproved','specification':None,'modal':None,'rules':[],'independent':None}
    try:e=Expression(code)
    except ValueError:
        outcome['reason']='invalid AST';return _wire(outcome)
    spec,sources=specification(e);outcome['specification']=spec
    expected={(v['path'],v['kind']) for v in spec['obligations']}
    hull={}
    todo=[(((0.,1.),(0.,1.)),0)]; transcript=hashlib.sha256(); boxes=0; count=0
    while todo:
        box,depth=todo.pop(); obligations=[]
        try:_interval(e.tree,box,obligations)
        except (ArithmeticError,OverflowError) as exc:
            if depth==MAX_DEPTH:
                outcome.update(boxes=boxes,obligations=count,reason=str(exc));return _wire(outcome)
            dim=depth%2; lo,hi=box[dim];mid=(lo+hi)/2
            for span in ((mid,hi),(lo,mid)):
                child=list(box);child[dim]=span;todo.append((tuple(child),depth+1))
            continue
        if {(path,kind) for path,kind,_ in obligations}!=expected or len(obligations)!=len(expected):raise RuntimeError('incomplete interval obligations')
        for path,kind,(lo,hi) in obligations:
            old=hull.get((path,kind),(lo,hi));hull[path,kind]=(min(lo,old[0]),max(hi,old[1]))
        transcript.update(_wire([box,obligations]).encode());boxes+=1;count+=len(obligations)
    modal=modal_certificate(sorted(expected));rules=[]
    for (path,kind),(lo,hi) in sorted(hull.items()):
        if path!='root' and kind!='nonzero':continue
        if kind=='nonzero' and lo<=0<=hi:continue
        src=sources[path+'.1' if kind=='nonzero' else path]
        rule={'kind':kind,'expression':src,'lower':lo,'upper':hi,'domain':spec['domain']}
        rule['id']=_digest(rule);rules.append(rule)
    from .interval_checker import check
    independent,checked_boxes=check(code,rules)
    ok=modal['holds'] and independent
    outcome.update(proved=ok,boxes=boxes,obligations=count,digest=transcript.hexdigest(),reason='proved totality and intermediate bounds' if ok else 'independent proof failed',modal=modal,rules=rules if ok else [],independent={'proved':independent,'boxes':checked_boxes,'method':'exact-rational-endpoints'})
    return _wire(outcome)


def prove(code):
    if not isinstance(code,str) or len(code)>2048:raise ValueError('invalid source')
    return json.loads(_prove(code))


def verify(code,certificate):
    try:return isinstance(certificate,dict) and certificate.get('proved') is True and _wire(certificate)==_wire(prove(code))
    except (ValueError,TypeError,RecursionError,OverflowError):return False


class RuleBook:
    """Bounded monotone learned theorems for exact source; no new trusted axioms.
    Revalidated on read; snapshots are authenticated by the owning archive.
    Capacity stops learning rather than silently replacing established facts.
    """
    LIMIT=32
    def __init__(self,state=None):
        self._entries={}
        if state is not None:
            if type(state) is not dict or set(state)!={'policy','entries'} or state['policy']!=POLICY or type(state['entries']) is not list or len(state['entries'])>self.LIMIT:raise ValueError('rule book contract')
            for row in state['entries']:
                if type(row) is not dict or set(row)!={'source','certificate'}:raise ValueError('invalid rule entry')
                if not self.learn(row['source'],row['certificate']):raise ValueError('duplicate rule entry')
    def lookup(self,code):
        raw=self._entries.get(code)
        return json.loads(raw) if raw is not None else None
    def learn(self,code,certificate):
        if not verify(code,certificate):raise ValueError('unproved new safety rule')
        if code in self._entries or len(self._entries)>=self.LIMIT:return False
        self._entries[code]=_wire(certificate);return True
    def matches(self,code):
        """Instantiate retained unconditional theorems at identical AST subtrees.
        Specific expressions, not generalized rewrite rules or new assumptions.
        """
        expr=Expression(code);spec,sources=specification(expr)
        index={}
        for src,raw in self._entries.items():
            cert=json.loads(raw)
            for rule in cert['rules']:
                index.setdefault(rule['expression'],{})[rule['id']]=rule
        result=[]
        for obligation in spec['obligations']:
            path=obligation.get('operand',obligation['path'])
            for ident,r in sorted(index.get(sources[path],{}).items()):
                if r['kind']==obligation['kind']:
                    result.append({'path':obligation['path'],'kind':r['kind'],'rule':ident})
        return result
    def snapshot(self):
        return {'policy':POLICY,'entries':[{'source':src,'certificate':json.loads(cert)} for src,cert in self._entries.items()]}
    @property
    def count(self):return len({r['id'] for c in self._entries.values() for r in json.loads(c)['rules']})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('expression');a=p.parse_args()
    result=prove(a.expression);print(json.dumps(result,indent=2));return 0 if result['proved'] else 1


if __name__=='__main__':raise SystemExit(main())
