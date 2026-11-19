"""Contract tests for the canonical OMEGA-X namespace and legacy entry points."""
from importlib import import_module
import json
import subprocess
import sys

import pytest


def invoke(module, *args):
    return subprocess.run(
        [sys.executable, '-m', module, *args],
        check=True, capture_output=True, text=True, timeout=30,
    )


def test_offline_core_has_no_upstream_import_side_effects():
    subprocess.run([sys.executable, '-c',
        'import sys; from omega_x_evolution.engine import Config; '
        'assert "shinka" not in sys.modules; assert Config().generations > 0'],
        check=True, capture_output=True, timeout=15)


@pytest.mark.parametrize('name', ['engine', 'checkpoint', 'workers', 'providers'])
def test_legacy_module_is_the_canonical_module(name):
    assert import_module(f'shinka.omega.{name}') is import_module(f'omega_x_evolution.{name}')


def test_cli_parity_with_multiprocessing():
    args = ('--seed', '5', '--generations', '2', '--evaluation-processes', '2')
    assert json.loads(invoke('omega_x_evolution', *args).stdout) == json.loads(invoke('shinka.omega', *args).stdout)


def test_resume_across_cli_names(tmp_path):
    db = tmp_path / 'run.db'
    key = tmp_path / 'key'
    key.write_bytes(b'k' * 32)
    settings = ('--seed', '5', '--islands', '2', '--workers', '2')
    checkpoint = ('--checkpoint', str(db), '--checkpoint-key-file', str(key))
    invoke('shinka.omega', *settings, '--generations', '2', *checkpoint)
    resumed = invoke('omega_x_evolution', *settings, '--generations', '4', '--resume', *checkpoint)
    uninterrupted = invoke('omega_x_evolution', *settings, '--generations', '4')
    assert json.loads(resumed.stdout) == json.loads(uninterrupted.stdout)
