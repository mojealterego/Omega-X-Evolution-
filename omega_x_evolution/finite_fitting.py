"""Exact bounded research models of first Fitting ideals of canonical modules.

Only the Artinian square-zero local algebras
    R = F_p[e_1,...,e_d]/(e_i*e_j for all i,j), 1 <= d <= 4
are supported. This model tests examples of arXiv:2608.03766v2; it does
NOT decide quasi-Gorensteinness for arbitrary Noetherian local rings.

All calculations are exact modular arithmetic and have strict size limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations, product
from math import factorial
from typing import Iterable

Element = tuple[int, ...]
Relation = tuple[Element, ...]


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    return all(n % factor for factor in range(2, int(n**0.5) + 1))


def _basis(vectors: Iterable[Element], p: int, width: int) -> tuple[Element, ...]:
    """Reduced row-echelon basis over a prime field, deterministic pivot order."""
    rows: dict[int, list[int]] = {}
    for raw in vectors:
        if type(raw) is not tuple or len(raw) != width or any(type(x) is not int or not 0 <= x < p for x in raw):
            raise ValueError('invalid finite-field vector')
        row = list(raw)
        for pivot, existing in sorted(rows.items()):
            scale = row[pivot]
            if scale:
                row = [(x - scale * y) % p for x, y in zip(row, existing)]
        pivot = next((i for i, value in enumerate(row) if value), None)
        if pivot is None:
            continue
        inv = pow(row[pivot], -1, p)
        row = [(v * inv) % p for v in row]
        for existing in rows.values():
            scale = existing[pivot]
            if scale:
                existing[:] = [(x - scale * y) % p for x, y in zip(existing, row)]
        rows[pivot] = row
    return tuple(tuple(rows[pivot]) for pivot in sorted(rows))


@dataclass(frozen=True, slots=True)
class SquareZeroLocalAlgebra:
    """Finite commutative local F_p-algebra of dimension (1 + embedding_dim)."""

    prime: int
    embedding_dim: int

    def __post_init__(self) -> None:
        if (type(self.prime) is not int or not 2 <= self.prime <= 11
                or not _is_prime(self.prime) or type(self.embedding_dim) is not int
                or not 1 <= self.embedding_dim <= 4):
            raise ValueError('bounded prime (2..11) and dimension (1..4) required')

    @property
    def zero(self) -> Element:
        return (0,) * (self.embedding_dim + 1)

    @property
    def one(self) -> Element:
        return (1,) + (0,) * self.embedding_dim

    def _valid(self, x: Element) -> None:
        if (type(x) is not tuple or len(x) != self.embedding_dim + 1
                or any(type(v) is not int or not 0 <= v < self.prime for v in x)):
            raise ValueError('invalid algebra element')

    def variable(self, i: int) -> Element:
        if type(i) is not int or not 0 <= i < self.embedding_dim:
            raise ValueError('invalid variable index')
        return tuple(1 if j == i+1 else 0 for j in range(self.embedding_dim+1))

    def add(self, a: Element, b: Element) -> Element:
        self._valid(a); self._valid(b)
        return tuple((x+y) % self.prime for x,y in zip(a,b))

    def neg(self, a: Element) -> Element:
        self._valid(a)
        return tuple(-x % self.prime for x in a)

    def mul(self, a: Element, b: Element) -> Element:
        self._valid(a); self._valid(b)
        p=self.prime
        return ((a[0]*b[0]) % p,) + tuple((a[0]*b[i] + a[i]*b[0]) % p
                                               for i in range(1, self.embedding_dim+1))

    def canonical_generators(self) -> tuple[Element, ...]:
        return tuple(self.variable(i) for i in range(self.embedding_dim))

    def canonical_action(self, scalar: Element, functional: Element) -> Element:
        """R-action on Hom_Fp(R,Fp), with coordinates dual to 1,e_i."""
        self._valid(scalar); self._valid(functional)
        p = self.prime
        constant = sum(s * f for s,f in zip(scalar,functional)) % p
        return (constant,) + tuple((scalar[0]*x) % p for x in functional[1:])

    def canonical_image(self, coefficients: tuple[Element,...]) -> Element:
        if type(coefficients) is not tuple or len(coefficients)!=self.embedding_dim:
            raise ValueError('canonical presentation arity')
        out = self.zero
        for coeff,gen in zip(coefficients,self.canonical_generators()):
            out = self.add(out, self.canonical_action(coeff,gen))
        return out

    def canonical_relations(self) -> tuple[Relation,...]:
        """Exact generators for ker(R^d -> omega), via cross and diagonal relations."""
        d=self.embedding_dim
        rel=[]
        for i in range(d):
            for j in range(d):
                if i!=j:
                    col=[self.zero for _ in range(d)]
                    col[i]=self.variable(j)
                    rel.append(tuple(col))
        for i in range(1,d):
            col=[self.zero for _ in range(d)]
            col[0]=self.neg(self.variable(0))
            col[i]=self.variable(i)
            rel.append(tuple(col))
        return tuple(rel)

    def _determinant(self, matrix: tuple[tuple[Element,...],...]) -> Element:
        n=len(matrix)
        if n==0:
            return self.one
        if n>3 or any(len(row)!=n for row in matrix):
            raise ValueError('determinant size exceeds bounded research contract')
        total=self.zero
        for perm in permutations(range(n)):
            inversions=sum(1 for i in range(n) for j in range(i+1,n) if perm[i]>perm[j])
            prod=self.one
            for i,j in enumerate(perm):
                prod=self.mul(prod,matrix[i][j])
            if inversions%2:
                prod=self.neg(prod)
            total=self.add(total,prod)
        return total

    def first_fitting_generators(self, relations: tuple[Relation,...] | None=None) -> tuple[Element,...]:
        """All (d-1)-minors of a presentation matrix, exactly over R."""
        columns=self.canonical_relations() if relations is None else relations
        d=self.embedding_dim
        if type(columns) is not tuple or len(columns)>32 or any(type(col) is not tuple or len(col)!=d for col in columns):
            raise ValueError('invalid bounded presentation')
        for col in columns:
            for entry in col:
                self._valid(entry)
        k=d-1
        if not k:
            return (self.one,)
        minors=[]
        for rows in combinations(range(d),k):
            for selected in combinations(range(len(columns)),k):
                minor=tuple(tuple(columns[j][i] for j in selected) for i in rows)
                minors.append(self._determinant(minor))
        return tuple(minors)

    def fitting_ideal_basis(self, relations: tuple[Relation,...] | None=None) -> tuple[Element,...]:
        """Vector-space basis of ideal generated by all first Fitting minors."""
        generators=self.first_fitting_generators(relations)
        ring_basis=(self.one,)+tuple(self.variable(i) for i in range(self.embedding_dim))
        products=(self.mul(a,b) for a in ring_basis for b in generators)
        return _basis(products,self.prime,self.embedding_dim+1)

    def span_elements(self, basis: tuple[Element,...]) -> set[Element]:
        for v in basis:
            self._valid(v)
        if len(basis)>4 or self.prime**len(basis)>20000:
            raise ValueError('span enumeration budget')
        p=self.prime
        return {tuple(sum(c*v[j] for c,v in zip(coeffs,basis)) % p
                      for j in range(self.embedding_dim+1))
                for coeffs in product(range(p), repeat=len(basis))}

    def relation_span_elements(self, relations: tuple[Relation,...]) -> set[tuple[Element,...]]:
        """Scalar span suffices: every canonical syzygy has entries in m, m^2=0."""
        flattened=tuple(tuple(x for entry in col for x in entry) for col in relations)
        independent=_basis(flattened,self.prime,self.embedding_dim*(self.embedding_dim+1))
        if self.prime**len(independent)>20000:
            raise ValueError('relation enumeration budget')
        p=self.prime;w=self.embedding_dim+1
        return {tuple(tuple(sum(c*v[j] for c,v in zip(coeffs,independent))%p
                            for j in range(i*w,(i+1)*w)) for i in range(self.embedding_dim))
                for coeffs in product(range(p),repeat=len(independent))}

    def canonical_module_span(self, gens: tuple[Element,...]) -> set[Element]:
        basis=(self.one,)+tuple(self.variable(i) for i in range(self.embedding_dim))
        spanning=(self.canonical_action(a,g) for g in gens for a in basis)
        return self.span_elements(_basis(spanning,self.prime,self.embedding_dim+1))

    def canonical_fitting_report(self) -> dict:
        relations=self.canonical_relations()
        valid=verify_presentation(self,relations)
        if not valid:
            raise ArithmeticError('canonical module presentation failed exact validation')
        ideal_basis=self.fitting_ideal_basis(relations)
        # Distinct finite cardinalities rule out isomorphism. For d=1 both
        # modules are explicitly free of rank one, hence isomorphic.
        iso = self.embedding_dim==1 and len(ideal_basis)==2
        return {'model':'square_zero_local_artinian_v1',
                'prime':self.prime,'embedding_dimension':self.embedding_dim,
                'socle_dimension':self.embedding_dim,
                'gorenstein':self.embedding_dim==1,
                'canonical_dimension':self.embedding_dim+1,
                'fitting_dimension':len(ideal_basis),
                'fitting_isomorphic_to_canonical':iso,
                'presentation_valid':valid,
                'automatic_proof':False,
                'scope':'finite_model_only'}


def verify_presentation(ring: SquareZeroLocalAlgebra, relations: tuple[Relation,...]) -> bool:
    """Check relation kernel exactly by field rank, not by trusting construction."""
    if type(ring) is not SquareZeroLocalAlgebra or type(relations) is not tuple:
        raise ValueError('invalid presentation inputs')
    d=ring.embedding_dim
    try:
        if any(type(col) is not tuple or len(col)!=d for col in relations):
            return False
        for col in relations:
            if ring.canonical_image(col)!=ring.zero:
                return False
        flats=(tuple(x for entry in col for x in entry) for col in relations)
        syzygy_rank=len(_basis(flats,ring.prime,d*(d+1)))
        # Image of R^d->omega has full dimension d+1: e_i^* and 1^*
        # are reached by the minimal generators and variable action.
        return syzygy_rank==d*(d+1)-(d+1)
    except ValueError:
        return False
