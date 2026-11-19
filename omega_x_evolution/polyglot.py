"""Typed, bounded unsigned-16 program evolution and portable code generation.

Only validated immutable IR is executed or emitted; no candidate source, shell,
filesystem or network operations occur in the generated programs.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import itertools
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

MASK = 65535
OPS = {'add': '+', 'sub': '-', 'mul': '*', 'xor': '^', 'and': '&', 'or': '|'}
LANGUAGES = ('python', 'c', 'cpp', 'javascript', 'go', 'java')
ATOMS = (('x',), ('y',), ('lit', 0), ('lit', 1), ('lit', MASK))


def _u16(value):
    if type(value) is not int or not 0 <= value <= MASK:
        raise ValueError('expected u16')
    return value


@dataclass(frozen=True)
class Program:
    tree: tuple

    def __post_init__(self):
        count = 0
        def check(t, depth):
            nonlocal count
            count += 1
            if count > 63 or depth > 8 or type(t) is not tuple or not t or type(t[0]) is not str:
                raise ValueError('IR bounds or shape')
            op = t[0]
            if op in ('x', 'y') and len(t) == 1: return
            if op == 'lit' and len(t) == 2: _u16(t[1]); return
            if op in OPS and len(t) == 3:
                check(t[1], depth+1); check(t[2], depth+1); return
            raise ValueError('unknown IR operation')
        check(self.tree, 0)

    @property
    def size(self):
        def count(t): return 1 if t[0] not in OPS else 1+count(t[1])+count(t[2])
        return count(self.tree)


def _validated_tree(program: Program) -> tuple:
    # The frozen dataclass is not a security boundary: direct mutation and
    # subclass constructors can bypass its original validation. Snapshot the
    # immutable, recursively checked tree before consuming or emitting it.
    if type(program) is not Program:
        raise ValueError('validated Program required')
    tree = program.tree
    Program(tree)
    return tree


def evaluate(program: Program, x: int, y: int) -> int:
    tree = _validated_tree(program)
    _u16(x); _u16(y)
    return _evaluate_tree(tree, x, y)


def _evaluate_tree(tree: tuple, x: int, y: int) -> int:
    def walk(t):
        op = t[0]
        if op == 'x': return x
        if op == 'y': return y
        if op == 'lit': return t[1]
        a, b = walk(t[1]), walk(t[2])
        return {'add': lambda: a+b, 'sub': lambda: a-b, 'mul': lambda: a*b,
                'xor': lambda: a^b, 'and': lambda: a&b, 'or': lambda: a|b}[op]() & MASK
    return walk(tree)


def _expression(tree, language):
    op = tree[0]
    if op in ('x', 'y'): return op
    if op == 'lit':
        v = str(tree[1])
        if language in ('c', 'cpp'): return f'UINT32_C({v})'
        if language == 'go': return f'lit({v})'
        return v
    a, b = (_expression(t, language) for t in tree[1:])
    mask = 'UINT32_C(65535)' if language in ('c','cpp') else '65535'
    # C/C++/Go operations use uint32. JS arithmetic intermediates are exact
    # integers <= 2**32; bit operations retain the low 16 bits.
    return f'(({a} {OPS[op]} {b}) & {mask})'


def emit(program: Program, language: str) -> str:
    if language not in LANGUAGES:
        raise ValueError('invalid backend or IR')
    expr = _expression(_validated_tree(program), language)
    if language == 'python': return f'def candidate(x, y):\n    return {expr}\n'
    if language == 'javascript': return f'function candidate(x, y) {{ return {expr}; }}\n'
    if language == 'java': return f'public class Candidate {{\n    public static int candidate(int x, int y) {{ return {expr}; }}\n}}\n'
    if language in ('c','cpp'):
        return f'#include <stdint.h>\nuint32_t candidate(uint32_t x, uint32_t y) {{ return {expr}; }}\n'
    return f'package main\n\nfunc lit(v uint32) uint32 {{ return v }}\nfunc candidate(x, y uint32) uint32 {{ return {expr} }}\n'


def _points(rows, width):
    if type(rows) is not tuple or not 1 <= len(rows) <= 512: raise ValueError('invalid observations')
    for row in rows:
        if type(row) is not tuple or len(row) != width: raise ValueError('invalid observation')
        for v in row: _u16(v)
    if len({r[:2] for r in rows}) != len(rows): raise ValueError('duplicate coordinates')
    return rows


def evolve(train, holdout, *, budget=256, seed=42):
    train = _points(train, 3); holdout = _points(holdout, 3)
    if {r[:2] for r in train} & {r[:2] for r in holdout}: raise ValueError('split overlap')
    if type(budget) is not int or not 1 <= budget <= 4096 or budget*len(train)>500_000 or type(seed) is not int or not 0<=seed<2**32:
        raise ValueError('search budget')
    rng = random.Random(seed)
    grammar = list(ATOMS) + [(op,a,b) for a,b,op in itertools.product(ATOMS[:2], ATOMS[:2], OPS)]
    grammar += [(op,a,b) for a,b,op in itertools.product(ATOMS, ATOMS, OPS) if a not in ATOMS[:2] or b not in ATOMS[:2]]
    # A target-independent compositional grammar plus elite mutations.
    pairs=grammar[5:29]
    grammar=list(dict.fromkeys(grammar+[(op,a,b) for a,b,op in itertools.chain(itertools.product(pairs,ATOMS[:2],OPS),itertools.product(ATOMS[:2],pairs,OPS))]))
    seen = set(); elite = []
    def matches(p, data): return sum(_evaluate_tree(p.tree,x,y)==z for x,y,z in data)
    def fitness(p):
        errors=[_evaluate_tree(p.tree,x,y)^z for x,y,z in train]
        return sum(v.bit_count() for v in errors), -sum(v==0 for v in errors)
    for i in range(budget):
        if i < 29: tree = grammar[i]
        elif i%2==0: tree = grammar[((i-29)//2+29)%len(grammar)]
        else:
            a = rng.choice(elite)[3].tree; b = rng.choice([r[3].tree for r in elite]+list(ATOMS))
            tree = (rng.choice(tuple(OPS)),a,b)
        if tree in seen: continue
        seen.add(tree)
        try: p = Program(tree)
        except ValueError: continue
        elite.append((fitness(p),p.size,repr(tree),p)); elite.sort(key=lambda r:r[:3]); elite=elite[:12]
    best = elite[0][3]
    return {'schema':'omega-u16-v1','dataset_sha256':hashlib.sha256(json.dumps([train,holdout],separators=(',',':')).encode()).hexdigest(),'seed':seed,'program':best.tree, 'attempts':budget, 'unique_attempts':len(seen), 'nodes':best.size,
            'training_matches':-elite[0][0][1], 'training_bit_errors':elite[0][0][0], 'training_samples':len(train),
            'holdout_matches':matches(best,holdout), 'holdout_samples':len(holdout)}


def verify_backends(program: Program, points):
    """Compile/run generated source only. Missing toolchains are explicit.

    Trusted locally installed toolchains required. No arbitrary compiler flags,
    paths or source supplied by candidates. Not an OS sandbox for toolchains.
    """
    program = Program(_validated_tree(program))
    points = _points(points, 2)
    expected = ''.join(f'{_evaluate_tree(program.tree,x,y)}\n' for x,y in points)
    result = {}
    for lang in LANGUAGES:
        compiler = {'python':sys.executable,'c':shutil.which('gcc'),'cpp':shutil.which('g++'),
                    'javascript':shutil.which('node'),'go':shutil.which('go'),'java':shutil.which('javac') if shutil.which('java') else None}[lang]
        if compiler is None: result[lang]='unavailable'; continue
        with tempfile.TemporaryDirectory(prefix='omega-ir-') as td:
            root=Path(td); src=emit(program,lang)
            if lang=='python':
                source=root/'candidate.py'; src+=''.join(f'print(candidate({x},{y}))\n' for x,y in points); command=[compiler,'-I',str(source)]
            elif lang=='javascript':
                source=root/'candidate.js';src+=''.join(f'console.log(candidate({x},{y}));\n' for x,y in points);command=[compiler,str(source)]
            elif lang=='java':
                source=root/'Candidate.java';src=src.rsplit('}',1)[0]+'public static void main(String[] args) {\n'+''.join(f'System.out.println(candidate({x},{y}));\n' for x,y in points)+'}\n}\n';command=[shutil.which('java'),'-cp',str(root),'Candidate']
            elif lang in ('c','cpp'):
                source=root/('candidate.c' if lang=='c' else 'candidate.cpp');binary=root/'candidate'
                src+='#include <stdio.h>\nint main(void) {\n'+''.join(f'printf("%u\\n", (unsigned)candidate({x}u,{y}u));\n' for x,y in points)+'return 0;\n}\n'
                command=[str(binary)]
            else:
                source=root/'candidate.go';binary=root/'candidate';src=src.replace('package main\n','package main\nimport "fmt"\n',1)
                src+='func main() {\n'+''.join(f'fmt.Println(candidate({x},{y}))\n' for x,y in points)+'}\n';command=[str(binary)]
            source.write_text(src,encoding='ascii')
            env={**{k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SYSTEMROOT','WINDIR','TEMP','TMP','GOROOT','GOCACHE') if k in os.environ},'GO111MODULE':'off','GOPROXY':'off','GOSUMDB':'off','GOTOOLCHAIN':'local','GOWORK':'off','GOFLAGS':''}
            if lang in ('c','cpp','go'):
                build=[compiler,'build','-o',str(binary),str(source)] if lang=='go' else [compiler,'-O2','-o',str(binary),str(source)]
                subprocess.run(build,cwd=root,env=env,check=True,capture_output=True,timeout=60)
            if lang=='java': subprocess.run([compiler,str(source)],cwd=root,env=env,check=True,capture_output=True,timeout=30)
            out=subprocess.run(command,cwd=root,env=env,check=True,capture_output=True,text=True,timeout=10)
            if out.stdout!=expected: raise RuntimeError(f'{lang} semantic mismatch')
            result[lang]='pass'
    return result


def parse_dataset(raw):
    if not isinstance(raw,str) or len(raw)>65536: raise ValueError('dataset size')
    try:
        obj=json.loads(raw)
        if set(obj)!= {'train','holdout'}: raise ValueError('dataset fields')
        train,holdout=(_points(tuple(tuple(r) for r in obj[k]),3) for k in ('train','holdout'))
        if {r[:2] for r in train}&{r[:2] for r in holdout}: raise ValueError('split overlap')
        return train,holdout
    except (TypeError,KeyError,RecursionError) as exc: raise ValueError('dataset shape') from exc


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=42);p.add_argument('--budget',type=int,default=1024);p.add_argument('--dataset',type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args()
    rng=random.Random(a.seed); coords=tuple(dict.fromkeys((rng.randrange(65536),rng.randrange(65536)) for _ in range(64)))
    rows=tuple((x,y,((x+y)^y)&MASK) for x,y in coords)
    if a.dataset:
        with a.dataset.open(encoding='utf-8') as f: train,held=parse_dataset(f.read(65537))
    else: train,held=rows[:32],rows[32:]
    report=evolve(train,held,budget=a.budget,seed=a.seed)
    program=Program(report['program']); report['source']={lang:emit(program,lang) for lang in LANGUAGES}
    if a.verify: report['backends']=verify_backends(program,tuple(r[:2] for r in held))
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
