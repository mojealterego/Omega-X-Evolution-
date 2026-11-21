"""Contract checks for durable, reproducible requested docs and seed logs."""
from pathlib import Path
import hashlib
import json
import math
import pytest

from scripts.ontos_phase0_seed_diagnostics import report as seed_report
from scripts.ontos_v59_v62_campaign import report as l9_report

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs'/'omega'


def test_diagram_has_five_channels_and_real_precommit_order():
    text=(DOC/'ONTOS_CHANNELS_A_E_SEQUENCE.md').read_text()
    assert 'sequenceDiagram' in text and 'K as Zewnętrzne Jądro Immunologiczne' in text
    for kind in 'ABCDE': assert f'{kind}:' in text
    for gate in ('pre-commit','IMMUNE_LOCKDOWN','VETO','HyperLTL','LEC/Z3'):
        assert gate in text


def test_energy_table_does_not_invent_watts_from_nanojoules():
    text=(DOC/'ONTOS_ENERGY_BOUNDARIES.md').read_text()
    assert 'P_accelerator_peak' in text and 'P_system_wall_plug' in text
    for substrate in ('H100','RRAM','SOT-MRAM','s-MTJ','CPO','QPU'):
        assert substrate in text
    assert text.count('UNKNOWN')>=15
    assert '347,92' in text and '28,21' in text


def test_v81_to_v87_have_independent_criteria_and_roadmap_refs():
    text=(DOC/'ONTOS_EXTENSIONS_V81_V87.md').read_text()
    for n in range(81,88):
        assert f'v{n}' in text
        assert f'EXT-0{n-80}' in text
    for dep in ('v63','v65','v67','v68','v69'):
        assert dep in text
    assert 'UNKNOWN' in text and 'GATE-09' in text


def test_seed_evidence_is_reproducible_from_real_code():
    path=DOC/'PHASE0_FAILURE_SEEDS_SUMMARY.json'
    observed=json.loads(path.read_text())
    generated=seed_report()
    raw=json.dumps(generated,sort_keys=True,indent=2,allow_nan=False)+'\n'
    assert observed['raw_json_sha256']==hashlib.sha256(raw.encode()).hexdigest()
    assert len(observed['rows'])==3
    for row in observed['rows']:
        assert row['floor_preserved']
        assert row['synthetic_memory_probe']['automatic_promotion'] is False
        assert row['observation_count']==240


def test_campaign_evidence_is_reproducible_from_real_code():
    source=json.loads((DOC/'ONTOS_V59_V62_L9_SUMMARY.json').read_text())
    generated=l9_report()
    raw=json.dumps(generated,sort_keys=True,indent=2,allow_nan=False)+'\n'
    assert source['full_campaign_sha256']==hashlib.sha256(raw.encode()).hexdigest()
    assert source['v59']['energy_end'] < source['v59']['energy_start']
    assert source['v60']['energy_end'] < source['v60']['energy_start']
    assert source['v61']['number_of_seeds']==30
    assert source['v62']['number_of_seeds']==30
    assert source['physical_validation'] is False
