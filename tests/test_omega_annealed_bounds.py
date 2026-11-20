import numpy as np
import pytest
from omega_x_evolution.annealed import ACTIONS, TensorTrain, policy, propose

PARENT = '-(x+y)'


@pytest.mark.parametrize('action', [-1, -6, 7, True, 1.0, '1'])
@pytest.mark.parametrize('association', [False, True])
def test_policy_rejects_invalid_action(action, association):
    row = {'action': action, 'parent': PARENT, 'reward': .5}
    with pytest.raises(ValueError):
        if association:
            policy(PARENT, [], associations=[{'record': row, 'weight': .5}])
        else:
            policy(PARENT, [row])


@pytest.mark.parametrize('reward', [float('nan'), float('inf'), -float('inf'), 1.01, -1.01, True, '0.5'])
@pytest.mark.parametrize('association', [False, True])
def test_policy_rejects_invalid_reward(reward, association):
    row = {'action': 0, 'parent': PARENT, 'reward': reward}
    with pytest.raises(ValueError):
        if association:
            policy(PARENT, [], associations=[{'record': row, 'weight': .5}])
        else:
            policy(PARENT, [row])


@pytest.mark.parametrize('weight', [-.01, 1.01, float('nan'), float('inf'), True, '0.5'])
def test_policy_rejects_invalid_association_weight(weight):
    row = {'action': 0, 'parent': PARENT, 'reward': .5}
    with pytest.raises(ValueError):
        policy(PARENT, [], associations=[{'record': row, 'weight': weight}])


def test_policy_preserves_non_tensor_sentinel_and_positive_exploration():
    ignored = {'action': ACTIONS, 'parent': PARENT, 'reward': 1.}
    assert policy(PARENT, [ignored], associations=[{'record': ignored, 'weight': 1.}]) == policy(PARENT, [])
    row = {'action': 4, 'parent': PARENT, 'reward': .8}
    p = policy(PARENT, [row] * 12, temperature=.15, associations=[{'record': row, 'weight': .5}])
    assert sum(p) == pytest.approx(1.) and min(p) >= .1 / ACTIONS and p[4] > p[0]
    assert propose(PARENT, 4, 123) == propose(PARENT, 4, 123)


def test_tensor_exact_rank_one():
    tensor = np.einsum('i,j,k->ijk', np.arange(4.)+1, np.arange(4.)+2, np.arange(6.)+3)
    tt = TensorTrain.fit(tensor, 2)
    assert tt.parameters < tensor.size
    assert all(tt.at(*idx) == pytest.approx(tensor[idx]) for idx in np.ndindex(tensor.shape))
