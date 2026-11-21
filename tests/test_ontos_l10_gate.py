"""The gate must not reinterpret a simulated PASS as production verification."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_l10_gate_has_scoped_model_pass_but_blocks_full_claim():
    data=json.loads((ROOT/'docs/omega/ONTOS_L10_V63_V67_GATES.json').read_text())
    assert data['schema']=='ontos-l10-closeout-v1'
    assert data['model_gate']['status']=='PASS'
    assert data['full_l10_gate']['status']=='BLOCKED'
    assert data['full_l10_gate']['native_rust_zenoh_wasi_verified'] is False
    assert data['full_l10_gate']['physical_fpga_verified'] is False
    assert data['full_l10_gate']['source_suite_d_reproduced'] is False
    assert len(data['full_l10_gate']['unverified_properties'])>=4
    assert data['main_branch_only'] is True


def test_l10_gate_requires_real_test_log_and_byte_sha():
    data=json.loads((ROOT/'docs/omega/ONTOS_L10_V63_V67_GATES.json').read_text())
    assert data['evidence']['pytest']['result']=='PASS'
    assert data['evidence']['go_race']['result']=='PASS'
    assert data['evidence']['pytest']['count']>=299
    for item in ('pytest','go_race','q16_red','q16_green'):
        log=data['evidence'][item]
        path=ROOT/log['path']
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest()==log['sha256']
    assert 'passed' in (ROOT/data['evidence']['pytest']['path']).read_text()


def test_l10_gate_binds_actual_modules_and_hardware_fixtures():
    data=json.loads((ROOT/'docs/omega/ONTOS_L10_V63_V67_GATES.json').read_text())
    assert len(data['source_sha256'])>=12
    for name,expected in data['source_sha256'].items():
        path=ROOT/name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==expected


def test_l10_report_explicitly_discloses_rollback_boundary():
    doc=(ROOT/'docs/omega/ONTOS_L10_V63_V67_CLOSEOUT.md').read_text()
    for text in ('GATE-09', '303/303', 'rollback', 'Go', 'Zenoh', 'WASI', 'Q16.16', 'HYPERLTL', 'BLOCKED', 'PRODUCTION-VERIFIED'):
        assert text in doc
    assert 'PASS' in doc
