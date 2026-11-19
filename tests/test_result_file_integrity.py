"""Generated evaluation files must be treated as untrusted input."""

from pathlib import Path

import pytest

from shinka.utils.general import load_results


def test_malformed_correct_json_is_rejected(tmp_path: Path):
    (tmp_path / "correct.json").write_text('{"correct":', encoding="utf-8")
    result = load_results(str(tmp_path))
    assert result["correct"]["correct"] is False


@pytest.mark.parametrize("value", ['"true"', "1", "null", "[]"])
def test_nonboolean_correct_field_is_rejected(tmp_path: Path, value: str):
    (tmp_path / "correct.json").write_text(f'{{"correct": {value}}}', encoding="utf-8")
    assert load_results(str(tmp_path))["correct"]["correct"] is False


def test_nonobject_metrics_are_rejected(tmp_path: Path):
    (tmp_path / "metrics.json").write_text('[1,2,3]', encoding="utf-8")
    assert load_results(str(tmp_path))["metrics"] == {}


def test_successful_valid_evaluation_keeps_extra_metadata(tmp_path: Path):
    (tmp_path / "correct.json").write_text('{"correct": true, "reason": "pass"}', encoding="utf-8")
    (tmp_path / "metrics.json").write_text('{"score": 12}', encoding="utf-8")
    result = load_results(str(tmp_path))
    assert result["correct"] == {"correct": True, "reason": "pass"}
    assert result["metrics"] == {"score": 12}


def test_log_tail_is_bounded_without_losing_full_disk_log(tmp_path: Path):
    full = "abcd" * 100
    (tmp_path / "job_log.out").write_text(full, encoding="utf-8")
    result = load_results(str(tmp_path), max_log_bytes=20)
    assert result["stdout_log"].endswith(full[-20:])
    assert "skipped 380 earlier log bytes" in result["stdout_log"]
    assert (tmp_path / "job_log.out").read_text() == full


def test_oversized_result_json_is_rejected(tmp_path: Path):
    (tmp_path / "correct.json").write_text('{"correct": true}', encoding="utf-8")
    assert load_results(str(tmp_path), max_json_bytes=8)["correct"]["correct"] is False
