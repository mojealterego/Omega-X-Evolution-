"""Finite tests for Lu, arXiv:2609.11219v4, non-top image only."""
from __future__ import annotations

from itertools import product
from math import comb

import pytest

from omega_x_evolution.finite_box_local_cohomology import FiniteBox, NonTopImage, validate_multigraded_dimensions


def test_non_top_chain_inclusion_and_dimension():
    box = FiniteBox((1, 1, 1))
    assert [box.upper_vertices(i) for i in range(3)] == [
        ((1, 1, 1),),
        ((0, 1, 1), (1, 0, 1), (1, 1, 0), (1, 1, 1)),
        tuple(a for a in product(range(2), repeat=3) if any(a)),
    ]
    assert tuple(box.global_dimension(i) for i in range(3)) == (0, 1, 2)


@pytest.mark.parametrize('bounds', [(0,), (1,), (0,2), (1,2), (0,1,2), (2,3,1), (0,0,0), (2,2,2,2)])
def test_non_top_global_dimension_bounded_combinatorics(bounds):
    box = FiniteBox(bounds)
    for i in range(box.n):
        q = box.n - i
        admissible = box.upper_vertices(i)
        expected = max((sum(a[j] < bounds[j] for j in range(box.n))
                        for a in admissible), default=None)
        assert box.global_dimension(i) == expected
        assert box.global_dimension(i) == (None if expected is None else min(
            sum(x>0 for x in bounds), sum(x>0 for x in bounds)+i+sum(x>=2 for x in bounds)-box.n))


def test_zero_non_top_category_when_box_has_too_few_nonzero_coordinates():
    box=FiniteBox((1,0,0))
    assert box.upper_vertices(0)==()
    assert box.upper_vertices(1)==()
    assert box.global_dimension(0) is None
    assert box.global_dimension(1) is None
    assert box.is_non_top_image(1, {(0,0,0):0})
    assert not box.is_non_top_image(1, {(1,0,0):1})


def test_non_top_admission_and_filtration():
    box=FiniteBox((1,1,1))
    dim={(1,1,1):3,(0,1,1):2,(1,1,0):1}
    assert box.is_non_top_image(1,dim)
    assert not box.is_non_top_image(0,dim)
    layers=box.support_filtration(1,dim)
    assert layers[0]=={(1,1,1):3}
    assert layers[1]==dim
    assert list(box.support_filtration(2,{(1,0,0):4})[0].values())==[]
    assert box.support_filtration(2,{(1,0,0):4})[-1]=={(1,0,0):4}


def test_attached_primes_of_projective_cover_preserves_distinct_coordinate_primes():
    box=FiniteBox((1,1,1))
    primes=box.attached_primes_from_projective_cover(1,{(1,1,0):2,(1,1,1):1,(0,1,1):0})
    assert primes==frozenset({(0,1),(0,1,2)})


@pytest.mark.parametrize('i,a,expected',[
    (1,(1,1,1),(1,3,2)),
    (0,(1,1,1),(1,3,3,1)),
    (2,(1,1,1),(1,1)),
    (1,(1,1,0),(1,2,1)),
])
def test_injective_bass_numbers_from_paper(i,a,expected):
    box=FiniteBox((1,1,1))
    assert box.injective_bass_numbers(i,a)==expected


@pytest.mark.parametrize('a',[(0,0,0),(1,0,0),(1,1,0),(1,1,1)])
def test_projective_bass_numbers_are_koszul_binomial(a):
    box=FiniteBox((1,1,1))
    r=sum(x>0 for x in a)
    assert box.projective_bass_numbers(a)==tuple(comb(r,p) for p in range(r+1))


def test_abelian_non_top_is_not_top_degree_claim():
    box=FiniteBox((1,1))
    assert box.is_non_top_image(1,{(1,1):1})
    with pytest.raises(ValueError):
        box.upper_vertices(box.n)
    with pytest.raises(ValueError):
        box.global_dimension(box.n)


@pytest.mark.parametrize('bounds', [(), (True,), (1,-1), (1,1.5),(4096,), (1,)*9, (8,)*5])
def test_invalid_boxes_fail_closed(bounds):
    with pytest.raises((TypeError,ValueError)):
        FiniteBox(bounds)


@pytest.mark.parametrize('i',[-1,3,True,1.5])
def test_invalid_cohomology_degree(i):
    with pytest.raises((TypeError,ValueError)):
        FiniteBox((1,1,1)).upper_vertices(i)


def test_invalid_grading_data_rejected_not_silently_truncated():
    box=FiniteBox((1,1))
    for values in [{(1,1):-1},{(1,1):True},{(2,0):1},{(1,):1}, {(1,0):1.0}, {(1,0):1<<30}]:
        with pytest.raises((TypeError,ValueError)):
            box.is_non_top_image(1, values)
    with pytest.raises((ValueError,TypeError)):
        validate_multigraded_dimensions(box, [1,2])


def test_projective_cover_invalid_multiplicities_and_vertices():
    box=FiniteBox((1,1))
    for a in ({(0,0):1}, {(1,1):-1},{(1,1):True},{(5,1):1}):
        with pytest.raises((TypeError,ValueError)):
            box.attached_primes_from_projective_cover(1,a)


def test_zero_multiplicities_have_empty_attached_primes():
    box=FiniteBox((1,1))
    assert box.attached_primes_from_projective_cover(1,{})==frozenset()
    assert box.attached_primes_from_projective_cover(1,{(1,1):0})==frozenset()


@pytest.mark.parametrize('i,a',[(0,(1,0,0)),(1,(1,0,0)),(2,(0,0,0))])
def test_injective_bass_excludes_vertices_outside_category(i,a):
    with pytest.raises(ValueError):
        FiniteBox((1,1,1)).injective_bass_numbers(i,a)


def test_non_top_image_immutable_report_is_reproducible():
    box=FiniteBox((2,1,0))
    x=NonTopImage(box,1)
    assert x.degree==1
    assert x.q==2
    assert x.allowed_vertices==((1,1,0),(2,1,0))
    assert x.global_dimension==1
    assert x==NonTopImage(box,1)


def test_explicit_resource_limits():
    assert len(FiniteBox((2,2,2)).vertices())==27
    with pytest.raises(ValueError):
        FiniteBox((7,7,7,7,7))


def test_all_non_top_support_layers_partition_box_by_support_rank():
    box=FiniteBox((2,1,2))
    unions=set()
    for i in range(box.n):
        sup=set(box.upper_vertices(i))
        assert unions <= sup
        unions=sup
    assert unions==set(box.vertices())-{(0,0,0)}


def test_injective_bass_alt_sum_euler_characteristic():
    # Independent Euler-characteristic check of the proposed finite resolutions.
    for n in range(1,6):
        box = FiniteBox((1,)*n)
        for i in range(n):
            for a in box.upper_vertices(i):
                seq=box.injective_bass_numbers(i,a)
                assert sum((-1)**k * v for k,v in enumerate(seq)) == 0


def test_bounded_randomized_global_dimension_oracle():
    # Independent enumeration of maxima versus Lu's closed formula.
    import random
    rng=random.Random(0xD4C)
    for _ in range(300):
        bounds=tuple(rng.randrange(0,5) for _ in range(rng.randrange(1,6)))
        box=FiniteBox(bounds)
        for i in range(box.n):
            allowed=box.upper_vertices(i)
            expected=max((sum(a[j]<bounds[j] for j in range(box.n))
                          for a in allowed),default=None)
            assert box.global_dimension(i)==expected
