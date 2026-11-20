import pytest
from omega_x_evolution.holographic import CAPACITY, TRANSFER, bounded_records, Memory, trajectory


@pytest.mark.parametrize('foreign_count', [9, 63, 64, 65, 100])
def test_foreign_batch_above_protocol_limit_rejected(foreign_count):
    with pytest.raises(ValueError, match='foreign trajectory limit'):
        bounded_records(list(range(80)), list(range(foreign_count)))


@pytest.mark.parametrize('local_count', [0, 1, 55, 56, 63, 64, 65, 130])
@pytest.mark.parametrize('foreign_count', range(TRANSFER + 1))
def test_valid_batches_preserve_order_and_capacity(local_count, foreign_count):
    local = [('local', i) for i in range(local_count)]
    foreign = [('foreign', i) for i in range(foreign_count)]
    result = bounded_records(local, foreign)
    assert result == local[max(0, local_count - (CAPACITY - foreign_count)):] + foreign
    assert len(result) <= CAPACITY
    assert len(local) == local_count and len(foreign) == foreign_count


def test_memory_accepts_full_legal_batch():
    def row(i, island):
        return trajectory(str(i), island, 'p', '-(x+y)', '-(x+y+1)', 0, True, .8, .5, 3)
    result = bounded_records([row(i, 0) for i in range(80)], [row(i, 1) for i in range(TRANSFER)])
    memory = Memory(result)
    assert len(memory.records) == CAPACITY
    assert len(memory.retrieve('-(x+y)', CAPACITY)) == CAPACITY
    assert sum(x['weight'] for x in memory.retrieve('-(x+y)', CAPACITY)) == pytest.approx(1.)
