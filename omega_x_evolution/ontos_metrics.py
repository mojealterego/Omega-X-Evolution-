"""Exact tiny string assembly and finite interventional information measures."""
import math
from functools import lru_cache
from .ontos_metabolism import channel, entropy, mix


def assembly(word):
    """Minimum distinct concatenations with reusable substrings; at most 8 symbols."""
    if type(word) is not str or not 1<=len(word)<=8 or not word.isascii() or not word.isalnum():
        raise ValueError('assembly domain')
    @lru_cache(None)
    def forms(s):
        if len(s)==1: return (frozenset(),)
        return tuple({a|b|{s} for i in range(1,len(s)) for a in forms(s[:i]) for b in forms(s[i:])})
    def midpoint(s):
        if len(s)==1: return set()
        i=len(s)//2
        return midpoint(s[:i])|midpoint(s[i:])|{s}
    return {'minimum':min(map(len,forms(word))),'heuristic':len(midpoint(word))}


def causal_information(g,partition):
    """Uniform interventions, uniform within each macrocell; CP=EI/log2(n)."""
    g=channel(g); n=len(g)
    if len(g[0])!=n or type(partition) is not tuple or not 1<=len(partition)<=n or any(type(c) is not tuple or not c or len(c)>n or any(type(i) is not int or not 0<=i<n for i in c) for c in partition):
        raise ValueError('partition shape')
    if sorted(i for c in partition for i in c)!=list(range(n)):
        raise ValueError('partition coverage')
    macro=tuple(tuple(math.fsum(g[i][j] for i in a for j in b)/len(a) for b in partition) for a in partition)
    def ei(matrix):
        k=len(matrix)
        return max(0.,entropy(mix((1/k,)*k,matrix))-math.fsum(entropy(row) for row in matrix)/k)
    micro_ei,macro_ei=ei(g),ei(macro)
    return {'micro_ei_bits':micro_ei,'macro_ei_bits':macro_ei,'delta_bits':macro_ei-micro_ei,'micro_cp':micro_ei/math.log2(n) if n>1 else 0.,'macro_cp':macro_ei/math.log2(len(macro)) if len(macro)>1 else 0.}
