"""Residual acceptance: production recovery and compositional synthesis."""
import subprocess
import sys

import pytest

from test_omega_final_gates import replicas


def test_terminal_round_keeps_polling_for_certified_catchup(tmp_path):
    from omega_x_evolution.bft import MAX_ROUND, leader, make_block, quorum
    from omega_x_evolution.bft_transport import _dispatch
    from omega_x_evolution.pacemaker import Pacemaker

    nodes = replicas(tmp_path)
    members = sorted(nodes)
    laggard = nodes[members[-1]]
    active = [nodes[k] for k in members[:-1]]
    state = laggard.inspect()['state']
    for _ in range(MAX_ROUND - 1):
        laggard.advance()
    clock = [0.0]
    network_available = [False]

    def call(peer, op, args):
        if not network_available[0]:
            raise OSError('partition')
        return _dispatch(nodes[peer], op, args)

    driver = Pacemaker(laggard, call, clock=lambda: clock[0], base_timeout=1., max_timeout=1.)
    clock[0] = 2.
    assert driver.tick()['status'] == 'round-limit'

    class Stop:
        polls = 0

        def is_set(self):
            return False

        def wait(self, _poll):
            self.polls += 1
            if self.polls == 1:
                # Honest quorum makes progress while laggard is partitioned.
                p = nodes[leader(state, 0)].propose(make_block(state, []), [n.status() for n in active])
                block = p['body']['block']
                pv = quorum(state, [n.prevote(p) for n in active], phase='prevote')
                pc = quorum(state, [n.precommit(block, pv) for n in active], phase='precommit')
                for n in active:
                    n.commit(block, pv, pc)
                network_available[0] = True
            return self.polls == 2

    stop = Stop()
    report = driver.run(stop, max_ticks=3)
    assert report['status'] == 'caught-up'
    assert laggard.inspect()['state']['height'] == 2
    assert laggard.inspect()['log'] == active[0].inspect()['log']


def test_offline_legacy_llm_module_and_embedding_resolver():
    script = '''
import sys
from shinka.llm.llm import extract_between, LLMClient
from shinka.embed.client import resolve_embedding_backend
assert extract_between('```cpp\\nx\\n```', '```cpp', '```', False) == 'x'
assert LLMClient().model_names
assert resolve_embedding_backend('local/text@http://localhost:8080/v1').provider == 'local_openai'
assert not any(x in sys.modules for x in ('anthropic', 'openai', 'google.genai', 'instructor'))
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_search_combines_two_novel_subtrees(tmp_path):
    from omega_x_evolution.architecture import Case
    from omega_x_evolution.architecture_search import Search
    from omega_x_evolution.architecture_synthesis import SynthesizedIndex, Plan
    from omega_x_evolution.graph_memory import GraphMemory

    memory = GraphMemory(tmp_path/'graph.db', b'm'*32, 'a')
    a = memory.add('artifact', 'alpha bridge catalyst', {})
    b = memory.add('artifact', 'beta bridge evidence', {})
    memory.link(a, 'supports', b)
    memory.add('artifact', 'temperature gamma unrelated', {})
    index = SynthesizedIndex(memory)
    splits = ((Case('alpha catalyst', b),), (Case('alpha bridge', b),), (Case('beta evidence', b),))
    search = Search(tmp_path/'search.db', b's'*32, index, *splits, budget=256, create=True)
    evaluated = []
    orig = search._evaluate

    def capture(plan, group):
        evaluated.append(plan.tree)
        return orig(plan, group)

    search._evaluate = capture
    search.step(256)
    assert any(len(t) == 3 and len(t[1]) > 1 and len(t[2]) > 1 for t in evaluated)
    restarted = Search(tmp_path/'split.db', b's'*32, index, *splits, budget=256, create=True)
    restarted.step(127)
    restarted = Search(tmp_path/'split.db', b's'*32, index, *splits, budget=256)
    restarted.step(129)
    assert search.inspect() == restarted.inspect()
    assert search.finalize() == restarted.finalize()


def test_google_auth_configuration_without_sdk():
    script = '''
import os, sys
os.environ.pop('GOOGLE_GENAI_USE_VERTEXAI', None)
os.environ.pop('GEMINI_API_KEY', None)
from shinka.google_genai import google_genai_auth_mode, build_google_genai_client
assert google_genai_auth_mode() == 'api_key'
try:
    build_google_genai_client(auth_mode='api_key', api_key='')
except ValueError as exc:
    assert 'GEMINI_API_KEY' in str(exc)
else:
    raise AssertionError('credential check bypassed')
assert 'google.genai' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_upstream_runner_import_does_not_load_diff_parser():
    script = '''
import sys
from shinka.edit import summarize_diff
assert callable(summarize_diff)
assert 'unidiff' not in sys.modules
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_headless_provider_gateway_is_independent_of_cloud_sdks():
    script = '''
import sys
from shinka.llm.client import get_client_llm, get_async_client_llm
from shinka.llm.query import query, query_async
for get in (get_client_llm, get_async_client_llm):
    client, name, provider = get('headless/claude')
    assert client is None and name == 'headless/claude' and provider == 'headless'
assert callable(query) and callable(query_async)
assert not any(x in sys.modules for x in ('anthropic','openai','instructor','google.genai'))
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('faulty_index', range(4))
def test_certified_progress_despite_byzantine_rpc_and_transient_partition(tmp_path, faulty_index):
    from omega_x_evolution.bft import _header
    from omega_x_evolution.bft_transport import _dispatch
    from omega_x_evolution.pacemaker import Pacemaker

    nodes = replicas(tmp_path)
    pubs = sorted(nodes)
    faulty = pubs[faulty_index]
    honest = [p for p in pubs if p != faulty]
    clock = [0.0]
    healed = [False]

    def call(sender, peer, op, args):
        if peer == faulty:
            state = nodes[peer].inspect()['state']
            if op == 'view':
                # Signature is genuine but the claimed voter is another node.
                body = {**_header(state), 'round': args[1], 'phase': 'timeout', 'voter': honest[0]}
                vote = {'body': body, 'signature': nodes[peer].identity.sign(body)}
                return {'commit': None, 'timeout_vote': vote, 'timeout_certificate': {'round': args[1], 'votes': [vote]*3}}
            raise OSError('Byzantine withholding')
        if not healed[0] and (sender == honest[-1] or peer == honest[-1]):
            raise OSError('partition')
        return _dispatch(nodes[peer], op, args)

    drivers = {p: Pacemaker(nodes[p], lambda peer,op,args,p=p: call(p,peer,op,args), clock=lambda:clock[0],base_timeout=1.) for p in honest}
    for _ in range(4):
        for p in honest:
            drivers[p].tick()
        clock[0] += .5
    assert all(nodes[p].inspect()['state']['height'] == 1 and nodes[p].inspect()['round'] == 0 for p in honest)
    healed[0] = True
    for _ in range(24):
        for p in honest:
            drivers[p].tick()
        if all(nodes[p].inspect()['state']['height'] >= 2 for p in honest):
            break
        clock[0] += .25
    assert all(nodes[p].inspect()['state']['height'] >= 2 for p in honest)
    committed = [nodes[p].inspect()['log'][0] for p in honest]
    assert all(row == committed[0] for row in committed)
