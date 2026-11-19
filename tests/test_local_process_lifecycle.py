"""Regression tests for local evaluation process lifecycle and result integrity."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import time

import pytest

from shinka.launch.local import monitor, submit
from shinka.launch.scheduler import JobScheduler, LocalJobConfig
from shinka.utils.general import parse_time_to_seconds


def test_parse_time_rejects_negative_and_invalid_components():
    for value in ("-01:00:00", "01:60:00", "00:00:60", "01:-01:00", "not-a-time"):
        with pytest.raises(ValueError):
            parse_time_to_seconds(value)
    assert parse_time_to_seconds("25:00:01") == 90001


def test_timeout_reaps_process_and_descendants(tmp_path: Path):
    if os.name != "posix":
        pytest.skip("POSIX process group lifecycle assertion")
    parent_code = (
        "import subprocess,sys,time; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']); "
        "print(p.pid,flush=True);time.sleep(60)"
    )
    process = submit(str(tmp_path), [sys.executable, "-u", "-c", parent_code])
    result = monitor(process, str(tmp_path), timeout="00:00:01", poll_interval=0.05)
    assert process.poll() is not None
    assert all(file.closed for file in process.log_files)
    assert result["execution_status"] == "timed_out"
    assert result["correct"]["correct"] is False

    child_pid = int((tmp_path / "job_log.out").read_text().strip())
    import psutil
    child = psutil.Process(child_pid) if psutil.pid_exists(child_pid) else None
    assert child is None or child.status() == psutil.STATUS_ZOMBIE


def test_failed_process_cannot_report_success_from_leftover_files(tmp_path: Path):
    (tmp_path / "correct.json").write_text('{"correct": true}', encoding="utf-8")
    (tmp_path / "metrics.json").write_text('{"combined_score": 99}', encoding="utf-8")
    process = submit(
        str(tmp_path),
        [sys.executable, "-c", "import sys; sys.exit(7)"],
    )
    result = monitor(process, str(tmp_path), poll_interval=0.01)
    assert result["correct"]["correct"] is False
    assert result["metrics"].get("combined_score") != 99
    assert result["execution_status"] == "failed"
    assert result["return_code"] == 7


def test_crashed_evaluation_cannot_claim_success(tmp_path: Path):
    code = (
        "from pathlib import Path;import sys; "
        f"Path({str(tmp_path / 'correct.json')!r}).write_text('{{\"correct\": true}}'); "
        "sys.exit(3)"
    )
    process = submit(str(tmp_path), [sys.executable, "-c", code])
    result = monitor(process, str(tmp_path), poll_interval=0.01)
    assert result["correct"]["correct"] is False
    assert result["execution_status"] == "failed"


def test_async_cancellation_reaps_and_closes_logs(tmp_path: Path):
    scheduler = JobScheduler("local", LocalJobConfig())
    try:
        process = submit(str(tmp_path), [sys.executable, "-u", "-c", "import time;time.sleep(60)"])
        assert asyncio.run(scheduler.cancel_job_async(process))
        assert process.poll() is not None
        assert all(f.closed for f in process.log_files)
        result = monitor(process, str(tmp_path))
        assert result["execution_status"] == "cancelled"
    finally:
        scheduler.shutdown()


def test_sync_scheduler_enforces_local_timeout(tmp_path: Path):
    evaluate = tmp_path / "evaluate.py"
    evaluate.write_text("import time; time.sleep(60)", encoding="utf-8")
    scheduler = JobScheduler("local", LocalJobConfig(eval_program_path=str(evaluate), time="00:00:01"))
    try:
        start = time.monotonic()
        results, _ = scheduler.run("candidate.py", str(tmp_path / "run"))
        assert time.monotonic() - start < 10
        assert results["execution_status"] == "timed_out"
    finally:
        scheduler.shutdown()


def test_cleanup_logging_tolerates_thread_start_failure(tmp_path: Path):
    import threading
    from shinka.launch.local import ProcessWithLogging

    class FinishedProcess:
        pid = 123
        returncode = 0

    files = (
        (tmp_path / "stdout").open("w", encoding="utf-8"),
        (tmp_path / "stderr").open("w", encoding="utf-8"),
    )
    threads = (threading.Thread(target=lambda: None), threading.Thread(target=lambda: None))
    process = ProcessWithLogging(FinishedProcess(), files, threads)
    process.cleanup_logging()
    process.cleanup_logging()
    assert all(file.closed for file in files)
