"""Local evaluation process lifecycle and bounded-time result collection.

Local jobs execute generated (untrusted) code; process-group termination limits
runaway child processes but is not an operating-system sandbox. Use a container
or another external sandbox when the evaluation code is not trusted.
"""

import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Dict, Optional, TextIO, Tuple

from shinka.utils import load_results, parse_time_to_seconds

logger = logging.getLogger(__name__)


class ProcessWithLogging:
    """Wrap Popen with log drainage and whole-process-tree termination.

    All local child processes are started in a new POSIX session so a timeout
    or cancellation can kill their process group, not merely the root Python
    evaluator. The process itself is reaped before logging handles are closed.
    """

    def __init__(
        self,
        process: subprocess.Popen,
        log_files: Tuple[TextIO, TextIO],
        log_threads: Tuple[threading.Thread, threading.Thread],
    ) -> None:
        self.process = process
        self.log_files = log_files
        self.log_threads = log_threads
        self.termination_reason: Optional[str] = None
        self._terminate_lock = threading.Lock()
        self._logging_lock = threading.Lock()
        self._logging_closed = False

    def __getattr__(self, name):
        return getattr(self.process, name)

    def __str__(self) -> str:
        return f"ProcessWithLogging(PID: {self.process.pid})"

    def __repr__(self) -> str:
        return (
            f"ProcessWithLogging(PID: {self.process.pid}, "
            f"returncode: {self.process.returncode})"
        )

    def kill(self, *, reason: str = "killed") -> None:
        """Forcefully terminate an evaluation and its descendants; idempotent.

        A separate process group is mandatory on POSIX. On Windows, the
        process tree is traversed using the project's psutil dependency.
        """
        with self._terminate_lock:
            if self.process.poll() is None:
                if self.termination_reason is None:
                    self.termination_reason = reason
                if os.name == "posix":
                    try:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        logger.exception("Could not kill process group %s", self.pid)
                        self.process.kill()
                else:
                    try:
                        import psutil

                        parent = psutil.Process(self.pid)
                        children = parent.children(recursive=True)
                        for child in children:
                            try:
                                child.kill()
                            except psutil.NoSuchProcess:
                                pass
                        self.process.kill()
                    except (ImportError, OSError):
                        self.process.kill()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        self.cleanup_logging()

    def cleanup_logging(self) -> None:
        """Drain joined reader threads, then close files exactly once."""
        with self._logging_lock:
            if self._logging_closed:
                return
            for thread in self.log_threads:
                # Startup can fail before both worker threads are started.
                if thread.ident is not None:
                    thread.join(timeout=2.0)
            for handle in self.log_files:
                try:
                    handle.close()
                except OSError as exc:
                    logger.warning("Error closing log file: %s", exc)
            self._logging_closed = True


def _stream_output(pipe, file_handle: TextIO, verbose_prefix=None) -> None:
    """Continuously drain an evaluation pipe, preventing child pipe deadlocks."""
    try:
        for line in iter(pipe.readline, ""):
            file_handle.write(line)
            file_handle.flush()
            if verbose_prefix:
                logger.debug("%s: %s", verbose_prefix, line.strip())
    except (OSError, ValueError) as exc:
        logger.warning("Error draining evaluator output: %s", exc)
    finally:
        pipe.close()


def submit(
    log_dir: str,
    cmd: list[str],
    verbose: bool = False,
    env_overrides: Optional[Dict[str, str]] = None,
) -> ProcessWithLogging:
    """Start an evaluation with isolated process group and streamed logs.

    Old evaluation result files are invalidated before each new attempt, so
    reused work directories cannot return scores from earlier executions.
    """
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)

    for name in ("correct.json", "metrics.json"):
        (log_dir_path / name).unlink(missing_ok=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if env_overrides:
        env.update(env_overrides)

    stdout_file = (log_dir_path / "job_log.out").open("w", buffering=1, encoding="utf-8")
    try:
        stderr_file = (log_dir_path / "job_log.err").open("w", buffering=1, encoding="utf-8")
    except Exception:
        stdout_file.close()
        raise

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
            env=env,
            start_new_session=(os.name == "posix"),
        )
    except Exception:
        stdout_file.close()
        stderr_file.close()
        raise

    stdout_thread = threading.Thread(
        target=_stream_output,
        args=(process.stdout, stdout_file, "STDOUT" if verbose else None),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_stream_output,
        args=(process.stderr, stderr_file, "STDERR" if verbose else None),
        daemon=True,
    )
    wrapped = ProcessWithLogging(
        process, (stdout_file, stderr_file), (stdout_thread, stderr_thread)
    )
    try:
        stdout_thread.start()
        stderr_thread.start()
    except Exception:
        wrapped.kill(reason="startup_error")
        raise

    if verbose:
        logger.info("Submitted local process with PID: %s", process.pid)
        logger.info("Launched local command: %s", " ".join(cmd))
    return wrapped


def monitor(
    process: ProcessWithLogging,
    results_dir: str,
    poll_interval: float = 0.5,
    verbose: bool = False,
    timeout: Optional[str] = None,
) -> dict:
    """Wait for a local evaluation and reject failed or timed-out results."""
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    timeout_seconds = parse_time_to_seconds(timeout) if timeout is not None else None
    if verbose:
        logger.info("Monitoring local process with PID: %s...", process.pid)

    started = time.monotonic()
    try:
        while process.poll() is None:
            if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
                logger.warning("Process %s exceeded timeout %s", process.pid, timeout)
                process.kill(reason="timeout")
                break
            time.sleep(poll_interval)
        process.wait()
    finally:
        process.cleanup_logging()

    results = load_results(results_dir)
    return_code = process.returncode
    reason = process.termination_reason
    if reason == "timeout":
        status = "timed_out"
    elif reason == "cancelled":
        status = "cancelled"
    elif return_code == 0 and reason is None:
        status = "completed"
    else:
        status = "failed"

    if status != "completed":
        results["correct"] = {"correct": False}
        # Never use metrics from a crashed or terminated evaluator to select
        # winning programs, even if the evaluator wrote a success file first.
        results["metrics"] = {}
    results["execution_status"] = status
    results["return_code"] = return_code
    if verbose:
        logger.info("Process %s completed: %s (exit=%s)", process.pid, status, return_code)
    return results
