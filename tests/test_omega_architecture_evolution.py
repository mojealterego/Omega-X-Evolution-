"""v28: corpus-weighted retrieval and multi-source graph architectures."""
import math
import pytest
from omega_x_evolution.architecture import Case
from omega_x_evolution.architecture_synthesis import Plan, SynthesizedIndex
from omega_x_evolution.graph_memory import GraphMemory
from omega_x_evolution.streaming_synthesis import StreamingSearch, tree_at, tree_count


def graph(tmp_path):
    m = GraphMemory(tmp_path/'graph.db', b'm'*32, 'a')
    a = m.add('artifact', 'alpha red common', {})
    b = m.add('artifact', 'alpha blue common', {})
    c = m.add('artifact', 'target evidence rare rare rare common', {})
    d = m.add('artifact', 'distractor common', {})
    m.link(a, 'supports', c)
    m.link(b, 'supports', c)
    m.link(a, 'supports', d)
    return m, a, b, c, d


def test_v28_bm25_real_corpus_weighting(tmp_path):
    m, _, _, c, d = graph(tmp_path)
    idx = SynthesizedIndex(m)
    rows = idx.retrieve(Plan(('bm25',)), 'rare common')
    assert rows[0]['id'] == c
    scores = {r['id']: r['score'] for r in rows}
    assert 0 < scores[d] < scores[c] <= 1
    # Independent reference for BM25, normalized by maximal possible score.
    n = 4; avg = (3+3+6+2)/n; k = 1.2; b = .75
    idf = lambda df: math.log1p((n-df+.5)/(df+.5))
    term = lambda tf, dl: tf*(k+1)/(tf+k*(1-b+b*dl/avg))
    expected = (idf(1)*term(3,6)+idf(4)*term(1,6))/((idf(1)+idf(4))*(k+1))
    assert scores[c] == pytest.approx(expected, abs=1e-12)


def test_v28_diffusion_combines_sources_without_parallel_edge_amplification(tmp_path):
    m, a, b, c, d = graph(tmp_path)
    idx = SynthesizedIndex(m)
    plan = Plan(('diffuse', ('lex',)))
    rows = {r['id']:r for r in idx.retrieve(plan,'alpha')}
    # a distributes 0.5 across two destinations; b has one destination.
    assert rows[c]['score'] == pytest.approx(1-(1-.25)*(1-.5))
    assert rows[d]['score'] == pytest.approx(.25)
    assert rows[c]['supporting_nodes'] == sorted([a,b,c])
    m.link(a,'produced',c)
    other = {r['id']:r for r in SynthesizedIndex(m).retrieve(plan,'alpha')}
    assert other[c]['score'] == rows[c]['score']
    assert other[d]['score'] == rows[d]['score']
    assert all(0 < r['score'] <= 1 for r in other.values())


def test_v28_new_grammar_autonomous_search_and_resume(tmp_path):
    m = GraphMemory(tmp_path/'graph.db',b'm'*32,'a')
    a=m.add('artifact','alpha red signal',{})
    b=m.add('artifact','alpha blue signal',{})
    # Fix tie order to make single-source propagation strictly inferior.
    d,c=sorted(m.add('artifact',text,{}) for text in ('zircon','quartz'))
    m.link(a,'supports',c);m.link(b,'supports',c);m.link(a,'supports',d)
    idx = SynthesizedIndex(m)
    splits = ((Case('alpha',c),),(Case('red blue',c),),(Case('signal',c),))
    plans = {tree_at(2,16,i) for i in range(tree_count(2,16))}
    assert ('diffuse',('bm25',)) in plans
    search = StreamingSearch(tmp_path/'campaign.db', b's'*32,idx,*splits,create=True)
    search.step(10)
    search = StreamingSearch(tmp_path/'campaign.db',b's'*32,idx,*splits)
    search.step(30)
    other = StreamingSearch(tmp_path/'other.db',b's'*32,idx,*splits,create=True)
    other.step(40)
    assert search.inspect()==other.inspect()
    report=search.finalize()
    assert report==other.finalize()
    assert report['promoted'] and report['selected']==['diffuse',['lex']]
    assert report['test']['mrr']==pytest.approx(1/3)
    assert report['baseline_test']['mrr']==0
    assert report['test_evaluations']==2
    assert search.finalize()==report
    with pytest.raises(ValueError): search.step(1)


def test_v28_forged_plan_rejected_before_execution(tmp_path):
    m,*_=graph(tmp_path)
    idx=SynthesizedIndex(m)
    plan=Plan(('lex',))
    object.__setattr__(plan,'tree',('shell',))
    with pytest.raises(ValueError,match='invalid score program'):
        idx.retrieve(plan,'alpha')


def test_v28_json_parser_bounds_before_full_materialization():
    # An oversized tree must be rejected at the decoding boundary.
    branch=['lex']
    for _ in range(10): branch=['add',branch,branch]
    with pytest.raises(ValueError,match='bound'):
        Plan.from_json(branch)


def test_v28_diffuse_budget_admission(tmp_path, monkeypatch):
    from omega_x_evolution import architecture_synthesis as module
    m,*_=graph(tmp_path)
    idx=SynthesizedIndex(m)
    monkeypatch.setattr(module,'WORK_CAP',9)
    with pytest.raises(ValueError,match='retrieval work cap'):
        idx.retrieve(Plan(('diffuse',('lex',))),'alpha')
    assert idx.last_work<=11
    monkeypatch.setattr(module,'WORK_CAP',2_000_000)
    assert idx.retrieve(Plan(('diffuse',('lex',))),'alpha')


def test_v28_subclass_and_invalid_operator_types_rejected(tmp_path):
    m,*_=graph(tmp_path)
    idx=SynthesizedIndex(m)
    class Unchecked(Plan):
        def __post_init__(self):
            pass
    with pytest.raises(ValueError):idx.retrieve(Unchecked(('shell',)),'alpha')
    with pytest.raises(ValueError):Plan((['lex'],))
