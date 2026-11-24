"""Regression tests for the ONTOS-TDA input resource boundary."""
import io
import json
import sys
import subprocess
from pathlib import Path

import pytest

from omega_x_evolution.ontos_tda import main


@pytest.mark.parametrize('fmt', ['json', 'jsonl'])
def test_deep_json_fails_closed(fmt, tmp_path):
    source = tmp_path / 'nested.json'
    source.write_text('[' * 1500 + '0' + ']' * 1500, encoding='utf-8')
    run = subprocess.run([sys.executable, '-m', 'omega_x_evolution.ontos_tda',
                          '--input', str(source), '--format', fmt, '--dimensions', '2'],
                         cwd=Path(__file__).resolve().parents[1],
                         capture_output=True, text=True, timeout=8)
    assert run.returncode == 2
    assert not run.stdout
    assert 'Traceback' not in run.stderr
    assert 'JSON nesting exceeds latent input limit' in run.stderr


def test_jsonl_never_requests_an_unbounded_line(monkeypatch, capsys):
    class BoundedStream(io.BytesIO):
        def readline(self, size=-1):
            assert 0 < size <= 4097, 'unbounded read requested'
            return super().readline(size)

        def __iter__(self):
            raise AssertionError('unbounded iteration requested')

    stream = BoundedStream(b' ' * 100_000 + b'\n')

    def open_stream(self, mode='r', *args, **kwargs):
        assert mode == 'rb', 'JSONL must count bytes before decoding'
        return stream

    monkeypatch.setattr(Path, 'open', open_stream)
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', 'ignored',
                                    '--format', 'jsonl', '--dimensions', '2'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert 'line too long at 1' in captured.err


@pytest.mark.parametrize('newline', [b'\n', b'\r\n', b''])
def test_jsonl_exact_byte_limit_and_final_record(newline, monkeypatch, tmp_path, capsys):
    source = tmp_path / 'bounded.jsonl'
    row = b'[0,1]'
    source.write_bytes(b'[1,0]\n[0,0]\n' + row + b' ' * (4096 - len(row) - len(newline)) + newline)
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(source),
                                    '--format', 'jsonl', '--dimensions', '2'])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result['observed'] == 3
    assert result['release_authorized'] is False


@pytest.mark.parametrize('payload', [b'[1,2]\n' + b' ' * 4095 + b'\r\n', b'[1,2]\n\xff\n'],
                         ids=['oversize-crlf', 'invalid-utf8'])
def test_jsonl_invalid_bytes_or_oversize_crlf(payload, monkeypatch, tmp_path, capsys):
    source = tmp_path / 'bad.jsonl'
    source.write_bytes(payload)
    monkeypatch.setattr(sys, 'argv', ['tda', '--input', str(source),
                                    '--format', 'jsonl', '--dimensions', '2'])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert 'Traceback' not in captured.err
    if payload.endswith(b'\r\n'):
        assert 'line too long at 2' in captured.err
