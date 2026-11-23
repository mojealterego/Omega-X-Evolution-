"""Exact finite counterexample checks for arXiv:2608.03766v2.

These are executable *examples*, not an automated proof of Theorem 1.
"""
from __future__ import annotations

from itertools import product
import pytest

from omega_x_evolution.finite_fitting import SquareZeroLocalAlgebra, verify_presentation


@pytest.mark.parametrize('prime', [2, 3, 5, 7, 11])
@pytest.mark.parametrize('embedding_dim', [1, 2, 3, 4])
def test_fitting_criterion_exact_finite_models(prime, embedding_dim):
    algebra = SquareZeroLocalAlgebra(prime, embedding_dim)
    report = algebra.canonical_fitting_report()
    assert report['prime'] == prime
    assert report['embedding_dimension'] == embedding_dim
    assert report['canonical_dimension'] == embedding_dim + 1
    assert report['presentation_valid'] is True
    assert report['socle_dimension'] == embedding_dim
    assert report['gorenstein'] == (embedding_dim == 1)
    assert report['fitting_isomorphic_to_canonical'] == report['gorenstein']
    expected = (2 if embedding_dim == 1 else 2 if embedding_dim == 2 else 0)
    assert report['fitting_dimension'] == expected
    assert report['automatic_proof'] is False


@pytest.mark.parametrize('dim', [1, 2, 3, 4])
def test_relations_exactly_present_canonical_module(dim):
    ring = SquareZeroLocalAlgebra(3, dim)
    assert verify_presentation(ring, ring.canonical_relations())


def test_multiplication_associativity_and_commutativity():
    ring = SquareZeroLocalAlgebra(3, 2)
    values = list(product(range(3), repeat=3))
    for a in values:
        for b in values:
            assert ring.mul(a, b) == ring.mul(b, a)
            for c in values:
                assert ring.mul(ring.mul(a, b), c) == ring.mul(a, ring.mul(b, c))


def test_fitting_ideal_closed_under_arbitrary_scalar_multiplication():
    ring = SquareZeroLocalAlgebra(3, 2)
    basis = ring.fitting_ideal_basis()
    assert len(basis) == 2
    span = ring.span_elements(basis)
    for a in product(range(3), repeat=3):
        for b in span:
            assert ring.mul(a, b) in span


def test_exact_bruteforce_kernel_matches_relations():
    ring = SquareZeroLocalAlgebra(2, 2)
    columns = ring.canonical_relations()
    presentation_span = ring.relation_span_elements(columns)
    kernel = set()
    for flat in product(range(2), repeat=6):
        coefficients = (tuple(flat[:3]), tuple(flat[3:]))
        if ring.canonical_image(coefficients) == (0, 0, 0):
            kernel.add(coefficients)
    assert presentation_span == kernel
    assert len(kernel) == 8


@pytest.mark.parametrize('p,dim', [(0, 1), (1, 1), (4, 1), (9, 2), (True, 1), (2, 0), (3, 5), (3, True)])
def test_invalid_ring_definitions_fail_closed(p, dim):
    with pytest.raises((ValueError, TypeError)):
        SquareZeroLocalAlgebra(p, dim)


def test_invalid_relation_does_not_pass_validation():
    ring = SquareZeroLocalAlgebra(3, 2)
    relations = list(ring.canonical_relations())
    edited = list(relations[0])
    edited[0] = ring.one
    relations[0] = tuple(edited)
    assert not verify_presentation(ring, tuple(relations))


def test_permutation_of_relations_preserves_fitting_ideal():
    ring = SquareZeroLocalAlgebra(5, 2)
    original = ring.fitting_ideal_basis()
    flipped = ring.fitting_ideal_basis(tuple(reversed(ring.canonical_relations())))
    assert ring.span_elements(original) == ring.span_elements(flipped)


def test_all_minors_zero_when_three_or_more_minimal_generators():
    for dim in (3, 4):
        ring = SquareZeroLocalAlgebra(2, dim)
        assert all(m == ring.zero for m in ring.first_fitting_generators())


def test_canonical_module_requires_two_generators_for_dim_two():
    ring = SquareZeroLocalAlgebra(2, 2)
    gens = ring.canonical_generators()
    assert len(gens) == 2
    assert len(ring.canonical_module_span(gens)) == 8
    for gen in gens:
        assert len(ring.canonical_module_span((gen,))) == 4
