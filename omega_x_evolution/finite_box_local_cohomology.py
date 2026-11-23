"""Bounded, exact finite-box invariants from Dancheng Lu, arXiv:2609.11219v4.

Research model ONLY: non-top local cohomology image categories in multigraded
polynomial rings. Its support-based classifier assumes the finite-box equivalence
and theorems in the cited preprint, not a standalone proof. It does not compute
local cohomology, Ext, a projective cover, or the full representation maps.

Degree, multiplicity, resource bounds and top-degree exclusions are enforced.
All numeric calculations use integers (no float approximations).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import comb, prod
from typing import Mapping

Multidegree = tuple[int, ...]
MAX_COORDINATES = 8
MAX_BOX_VERTICES = 4096
MAX_MULTIPLICITY = 65535


def _degree(degree: object, n: int) -> Multidegree:
    if type(degree) is not tuple or len(degree) != n:
        raise ValueError("multidegree must be a tuple of the box dimension")
    if any(type(c) is not int or c < 0 for c in degree):
        raise ValueError("multidegree coordinates must be nonnegative integers")
    return degree


@dataclass(frozen=True, slots=True)
class FiniteBox:
    """P_t=[0,t] with an exact resource bound (n<=8, |P_t|<=4096)."""
    bounds: Multidegree

    def __post_init__(self) -> None:
        if type(self.bounds) is not tuple or not 1 <= len(self.bounds) <= MAX_COORDINATES:
            raise ValueError("bounds must be a nonempty tuple of at most 8 coordinates")
        if any(type(x) is not int or x < 0 for x in self.bounds):
            raise ValueError("bounds must contain only nonnegative integers")
        if prod(x+1 for x in self.bounds) > MAX_BOX_VERTICES:
            raise ValueError("finite box exceeds vertex budget")

    @property
    def n(self) -> int:
        return len(self.bounds)

    def vertices(self) -> tuple[Multidegree, ...]:
        return tuple(product(*(range(c+1) for c in self.bounds)))

    def _validate_i(self, i: int) -> None:
        if type(i) is not int or not 0 <= i < self.n:
            raise ValueError("non-top local cohomology degree must satisfy 0 <= i < n")

    def _validate_a(self, a: object) -> Multidegree:
        degree = _degree(a, self.n)
        if any(x > bound for x, bound in zip(degree, self.bounds)):
            raise ValueError("multidegree outside determining box")
        return degree

    def support_rank(self, a: Multidegree) -> int:
        degree=self._validate_a(a)
        return sum(x > 0 for x in degree)

    def upper_vertices(self, i: int) -> tuple[Multidegree, ...]:
        """U_{n-i}(t) for i<n (Theorem 4.1)."""
        self._validate_i(i)
        q=self.n-i
        return tuple(a for a in self.vertices() if sum(x>0 for x in a)>=q)

    def global_dimension(self, i: int) -> int | None:
        """Proposition 4.4, None for the zero image category."""
        self._validate_i(i)
        active=sum(x>0 for x in self.bounds)
        q=self.n-i
        if active < q:
            return None
        r=sum(x>=2 for x in self.bounds)
        return min(active, active+i+r-self.n)

    def is_non_top_image(self, i: int, dimensions: Mapping[Multidegree,int]) -> bool:
        """Theorem 4.1 support criterion for a VALID finite-box representation.

        Dimension vectors can always be realized by a zero-map representation.
        This function does not validate nontrivial structure maps.
        """
        self._validate_i(i)
        dims=validate_multigraded_dimensions(self, dimensions)
        q=self.n-i
        return all(not v or sum(x>0 for x in a)>=q for a,v in dims.items())

    def support_filtration(self, i: int, dimensions: Mapping[Multidegree,int]) -> tuple[dict[Multidegree,int], ...]:
        """Rank-layer supports of canonical subrepresentations, Corollary 4.8.

        Morphism maps are not computed. Nonzero dimensions only are returned.
        """
        self._validate_i(i)
        dims=validate_multigraded_dimensions(self,dimensions)
        if not self.is_non_top_image(i,dims):
            raise ValueError("input not in the proposed non-top image category")
        return tuple({a:v for a,v in dims.items() if v>0 and sum(x>0 for x in a)>=self.n-s}
                     for s in range(i+1))

    def attached_primes_from_projective_cover(
        self, i: int, multiplicities: Mapping[Multidegree,int]
    ) -> frozenset[tuple[int,...]]:
        """Theorem B: given TRUE minimal projective-cover multiplicities.

        It does not infer these multiplicities from a dimension vector.
        Prime (x_j : j in F) is represented by zero-based coordinate indices.
        """
        self._validate_i(i)
        ms=validate_multigraded_dimensions(self,multiplicities)
        q=self.n-i
        result=set()
        for a,multiplicity in ms.items():
            if sum(x>0 for x in a)<q:
                raise ValueError("projective-cover index outside U_{n-i}(t)")
            if multiplicity:
                result.add(tuple(j for j,v in enumerate(a) if v>0))
        return frozenset(result)

    def projective_bass_numbers(self, a: Multidegree) -> tuple[int,...]:
        """Bass numbers of the principal projective, Proposition 5.7."""
        r=self.support_rank(a)
        return tuple(comb(r,p) for p in range(r+1))

    def injective_bass_numbers(self, i: int, a: Multidegree) -> tuple[int,...]:
        """Bass numbers of principal injective of H_i(t), i<n (Prop. 5.7)."""
        self._validate_i(i)
        r=self.support_rank(a)
        q=self.n-i
        if r<q:
            raise ValueError("injective indecomposable vertex outside U_{n-i}(t)")
        s=r-q
        return (1,)+tuple(comb(r,s+p)*comb(s+p-1,s) for p in range(1,q+1))


def validate_multigraded_dimensions(
    box: FiniteBox, dimensions: Mapping[Multidegree,int]
) -> dict[Multidegree,int]:
    if not isinstance(box,FiniteBox):
        raise TypeError("finite box required")
    if not isinstance(dimensions,Mapping):
        raise TypeError("dimension mapping required")
    if len(dimensions)>MAX_BOX_VERTICES:
        raise ValueError("too many dimension entries")
    result={}
    for a,v in dimensions.items():
        a=box._validate_a(a)
        if type(v) is not int or not 0<=v<=MAX_MULTIPLICITY:
            raise ValueError("invalid or unbounded vector-space dimension")
        result[a]=v
    return result


@dataclass(frozen=True,slots=True)
class NonTopImage:
    """Immutable summary of category H_i(t) for finite-box non-top degree."""
    box: FiniteBox
    degree: int

    def __post_init__(self) -> None:
        if not isinstance(self.box,FiniteBox):
            raise TypeError("finite box required")
        self.box._validate_i(self.degree)

    @property
    def q(self) -> int:
        return self.box.n-self.degree

    @property
    def allowed_vertices(self) -> tuple[Multidegree,...]:
        return self.box.upper_vertices(self.degree)

    @property
    def global_dimension(self) -> int | None:
        return self.box.global_dimension(self.degree)
