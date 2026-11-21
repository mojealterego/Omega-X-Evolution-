"""Finite, observational-vs-interventional binary structural causal model.

Z is a randomized, independent instrument; latent response type U fixes
X(z) and Y(x). No adjustment of observational association substitutes do(X).
Pure scientific reference, never chooses or executes real-world actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product


_RESPONSE_SPACE = tuple(product((0, 1), repeat=4))


def response_space() -> tuple[tuple[int, int, int, int], ...]:
    """All 16 deterministic response-function types (x0,x1,y0,y1)."""
    return _RESPONSE_SPACE


@dataclass(frozen=True, slots=True)
class ResponseType:
    x0: int
    x1: int
    y0: int
    y1: int
    weight: Fraction

    def __post_init__(self) -> None:
        if (any(type(x) is not int or x not in (0, 1)
                for x in (self.x0, self.x1, self.y0, self.y1))
                or type(self.weight) is not Fraction
                or self.weight <= 0 or self.weight > 1
                or self.weight.denominator > 10**9):
            raise ValueError('bounded binary latent response type')

    def treatment(self, z: int) -> int:
        if type(z) is not int or z not in (0, 1):
            raise ValueError('invalid intervention on instrument')
        return self.x1 if z else self.x0

    def outcome(self, x: int) -> int:
        if type(x) is not int or x not in (0, 1):
            raise ValueError('invalid treatment intervention')
        return self.y1 if x else self.y0


@dataclass(frozen=True, slots=True)
class BinaryIVSCM:
    """Finite distribution over latent response types, U independent of Z."""
    types: tuple[ResponseType, ...]

    def __post_init__(self) -> None:
        if (type(self.types) is not tuple or not 1 <= len(self.types) <= 64
                or any(type(t) is not ResponseType for t in self.types)):
            raise ValueError('bounded SCM type collection')
        # Revalidate to defend even against post-construction field tampering.
        for t in self.types:
            ResponseType(t.x0, t.x1, t.y0, t.y1, t.weight)
        if sum((t.weight for t in self.types), Fraction(0)) != 1:
            raise ValueError('latent distribution must sum to one')

    def observational(self, z: int) -> tuple[Fraction, Fraction, Fraction, Fraction]:
        """P(X=x,Y=y | Z=z), indexed by 2*x+y (NOT do(X))."""
        self.__post_init__()
        if type(z) is not int or z not in (0, 1):
            raise ValueError('instrument must be binary')
        cells = [Fraction(0) for _ in range(4)]
        for t in self.types:
            x = t.treatment(z)
            cells[2*x + t.outcome(x)] += t.weight
        return tuple(cells)

    def observational_risk(self, z: int, treatment: int) -> Fraction | None:
        p = self.observational(z)
        if type(treatment) is not int or treatment not in (0, 1):
            raise ValueError('binary treatment required')
        denominator = p[2*treatment] + p[2*treatment+1]
        return p[2*treatment+1]/denominator if denominator else None

    def intervene(self, treatment: int) -> Fraction:
        """P(Y=1 | do(X=treatment)), integrating over the untouched U."""
        self.__post_init__()
        if type(treatment) is not int or treatment not in (0, 1):
            raise ValueError('binary do-treatment required')
        return sum((t.weight*t.outcome(treatment) for t in self.types), Fraction(0))

    def average_treatment_effect(self) -> Fraction:
        return self.intervene(1) - self.intervene(0)

    def harm_probability(self) -> Fraction:
        """P(Y(0)=1,Y(1)=0) for the declared latent model."""
        self.__post_init__()
        return sum((t.weight for t in self.types if t.y0 == 1 and t.y1 == 0),
                   Fraction(0))
