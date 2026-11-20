import pytest
from omega_x_evolution.architecture import Case
from omega_x_evolution.architecture_synthesis import SynthesizedIndex, Plan
from omega_x_evolution.graph_memory import GraphMemory


def test_streaming_synthesis_crosses_old_budget_with_small_durable_cursor(tmp_path):
    from omega_x_evolution.streaming_synthesis import StreamingSearch, tree_at, tree_count
    memory=GraphMemory(tmp_path/'graph.db',b'm'*32,'a')
    a=memory.add('artifact','alpha bridge catalyst',{})
    b=memory.add('artifact','beta bridge evidence',{})
    memory.link(a,'supports',b)
    index=SynthesizedIndex(memory)
    splits=((Case('alpha catalyst',b),),(Case('alpha bridge',b),),(Case('beta evidence',b),))
    path=tmp_path/'search.db'
    campaign=StreamingSearch(path,b's'*32,index,*splits,create=True)
    for _ in range(32):campaign.step(256)
    before=campaign.inspect();assert before['evaluations']==8192
    campaign=StreamingSearch(path,b's'*32,index,*splits)
    campaign.step(8);after=campaign.inspect()
    assert after['evaluations']==8200 and after['cursor']!=before['cursor']
    assert not {'queue','seen'}&after.keys()
    assert path.stat().st_size<200_000
    assert tree_count(1,16)==8
    assert tree_count(2,16)==24
    assert tree_count(3,16)==264
    assert len({tree_at(3,16,i) for i in range(tree_count(3,16))})==264
    assert all(Plan(tree_at(3,16,i)) for i in range(264))
    assert campaign.finalize()['test_evaluations']==2
    assert campaign.finalize()==campaign.inspect()['final']
    with pytest.raises(ValueError):campaign.step(1)


def test_streaming_chunking_replays_with_same_cursor_and_incumbent(tmp_path):
    from omega_x_evolution.streaming_synthesis import StreamingSearch
    memory=GraphMemory(tmp_path/'graph.db',b'm'*32,'a')
    a=memory.add('artifact','alpha bridge catalyst',{})
    b=memory.add('artifact','beta bridge evidence',{})
    memory.link(a,'supports',b)
    index=SynthesizedIndex(memory)
    splits=((Case('alpha catalyst',b),),(Case('alpha bridge',b),),(Case('beta evidence',b),))
    one=StreamingSearch(tmp_path/'one.db',b's'*32,index,*splits,create=True)
    two=StreamingSearch(tmp_path/'two.db',b's'*32,index,*splits,create=True)
    one.step(128);two.step(63);two.step(65)
    assert one.inspect()==two.inspect()
    assert one.finalize()==two.finalize()


def test_grammar_caps_and_transaction_guard(tmp_path):
    from omega_x_evolution.streaming_synthesis import StreamingSearch,tree_count,tree_at
    assert tree_count(3,0)==0
    assert tree_count(3,1)==192
    with pytest.raises(ValueError):tree_at(3,1,192)
    with pytest.raises(ValueError):tree_count(256,16)
    with pytest.raises(ValueError):tree_count(1,17)
    memory=GraphMemory(tmp_path/'graph.db',b'm'*32,'a')
    a=memory.add('artifact','alpha bridge catalyst',{})
    b=memory.add('artifact','beta bridge evidence',{})
    index=SynthesizedIndex(memory)
    splits=((Case('alpha catalyst',b),),(Case('alpha bridge',b),),(Case('beta evidence',b),))
    campaign=StreamingSearch(tmp_path/'db',b's'*32,index,*splits,create=True)
    initial=campaign.inspect()
    with pytest.raises(ValueError):campaign.step(257)
    with pytest.raises(ValueError):campaign.step(1,work_cap=3_999_999)
    assert campaign.inspect()==initial
    result=campaign.step(256,work_cap=4_000_000)
    assert result['completed']==1
    assert result['work']<=4_000_000
