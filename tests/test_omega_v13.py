import pytest
from omega_x_evolution.polyglot import Program, evaluate, emit, evolve, verify_backends, LANGUAGES


def test_modular_semantics_and_reject_injection():
    p = Program(('mul', ('add', ('x',), ('lit', 1)), ('y',)))
    assert evaluate(p, 65535, 7) == 0
    with pytest.raises(ValueError): Program(('lit', True))
    with pytest.raises(ValueError): Program(('exec', 'echo hi'))
    with pytest.raises(ValueError): evaluate(p, -1, 0)


def test_search_deterministic_and_holdout_not_used_for_selection():
    train = tuple((x, y, x ^ y) for x, y in [(9, 2), (1, 3), (0, 7)])
    a = evolve(train, ((65535, 32768, 32767),), budget=64)
    b = evolve(train, ((65535, 32768, 1),), budget=64)
    assert a == evolve(train, ((65535, 32768, 32767),), budget=64)
    assert a['program'] == b['program'] and a['holdout_matches'] == 1 and b['holdout_matches'] == 0
    assert a['attempts'] == 64
    with pytest.raises(ValueError): evolve(train, train)


def test_real_backends():
    p = Program(('xor', ('mul', ('x',), ('y',)), ('sub', ('x',), ('y',))))
    points = ((0, 65535), (65535, 65535), (32768, 2), (1234, 9876))
    r = verify_backends(p, points)
    assert set(r) == set(LANGUAGES)
    assert r['python'] == 'pass'
    assert all(v in ('pass', 'unavailable') for v in r.values())
    for lang in LANGUAGES: assert emit(p,lang)
    with pytest.raises(ValueError): emit(p,'shell')


def test_nested_search_and_constant_wraparound():
    import random
    rng=random.Random(123)
    rows=tuple((x,y,((x+y)^y)&65535) for x,y in ((rng.randrange(65536),rng.randrange(65536)) for _ in range(48)))
    a=evolve(rows[:32],rows[32:],budget=1024,seed=123)
    assert a['training_matches']==32 and a['holdout_matches']==16
    p=Program(('sub',('lit',0),('lit',1)))
    assert all(r in ('pass','unavailable') for r in verify_backends(p,((0,0),)).values())


def test_custom_json_bounded_and_java_backend():
    from omega_x_evolution.polyglot import parse_dataset
    train,held=parse_dataset('{"train":[[1,2,3]],"holdout":[[3,4,7]]}')
    assert train==((1,2,3),) and held==((3,4,7),)
    with pytest.raises(ValueError): parse_dataset('{"train":[[1,2,3]],"holdout":[[1,2,4]]}')
    assert 'java' in LANGUAGES
