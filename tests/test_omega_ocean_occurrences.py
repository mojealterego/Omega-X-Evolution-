"""Contract simulation of the Ocean SampleSet aggregation boundary."""
from types import ModuleType, SimpleNamespace
from contextlib import nullcontext
import sys
import pytest
import numpy as np
from omega_x_evolution.quantum import Problem, dwave_sample, hardware

P = Problem((10, 20), ((0,), (1,)), 1)


def install_contract(monkeypatch, rows):
    calls = []
    class SampleSet:
        def data(self, fields):
            for sample, count in rows:
                values = {'sample': sample, 'num_occurrences': count}
                yield SimpleNamespace(**{field: values[field] for field in fields})
    class Composite:
        def __init__(self, sampler):
            pass
        def sample_qubo(self, qubo, num_reads):
            calls.append((qubo, num_reads))
            return SampleSet()
    package = ModuleType('dwave')
    module = ModuleType('dwave.system')
    module.DWaveSampler = lambda **kwargs: nullcontext(object())
    module.EmbeddingComposite = Composite
    monkeypatch.setitem(sys.modules, 'dwave', package)
    monkeypatch.setitem(sys.modules, 'dwave.system', module)
    return calls


def test_aggregated_rows_expand_to_actual_reads(monkeypatch):
    calls = install_contract(monkeypatch, [({0: 1, 1: 0}, np.int64(2)), ({0: 0, 1: 1}, 1)])
    result = hardware(P, dwave_sample, authorized=True, reads=3)
    assert len(calls) == 1
    assert result['indices'] == [1]
    assert result['objective_evaluations'] == 3


def test_aggregate_overflow_rejected(monkeypatch):
    install_contract(monkeypatch, [({0: 1, 1: 0}, 2), ({0: 0, 1: 1}, 2)])
    with pytest.raises(ValueError, match='read cap'):
        hardware(P, dwave_sample, authorized=True, reads=3)


@pytest.mark.parametrize('count', [0, -1, 1.5, True, '2', 10**100])
def test_invalid_or_oversized_occurrences_rejected(monkeypatch, count):
    install_contract(monkeypatch, [({0: 1, 1: 0}, count)])
    with pytest.raises(ValueError):
        hardware(P, dwave_sample, authorized=True, reads=3)


def test_no_submission_without_authorization(monkeypatch):
    calls = install_contract(monkeypatch, [({0: 1, 1: 0}, 1)])
    with pytest.raises(PermissionError):
        hardware(P, dwave_sample, reads=1)
    assert calls == []


@pytest.mark.parametrize('sample', [{0: 1, 2: 0}, {0: 2, 1: 0}])
def test_invalid_sample_rejected(monkeypatch, sample):
    install_contract(monkeypatch, [(sample, 1)])
    with pytest.raises(ValueError):
        hardware(P, dwave_sample, authorized=True, reads=1)
