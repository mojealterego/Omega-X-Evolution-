"""Regression tests: untrusted values must never be interpreted as shell code."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from shinka.launch import slurm


def test_activation_script_does_not_execute_shell_substitution(tmp_path: Path):
    marker = tmp_path / "executed"
    script = slurm._build_activation_commands(
        activate_script=f"$(touch {marker})"
    )
    subprocess.run(["bash", "-c", script], capture_output=True, check=False)
    assert not marker.exists()


def test_conda_name_does_not_allow_command_separator(tmp_path: Path):
    marker = tmp_path / "executed"
    script = slurm._build_activation_commands(
        conda_env=f"shinka; touch {marker}"
    )
    subprocess.run(["bash", "-c", script], capture_output=True, check=False)
    assert not marker.exists()


def test_environment_exports_do_not_execute_shell_substitution(tmp_path: Path):
    marker = tmp_path / "executed"
    script = slurm._render_env_exports({"CUSTOM_ARG": f"$(touch {marker})"})
    completed = subprocess.run(
        ["bash", "-c", f"{script}; printf '%s' \"$CUSTOM_ARG\""],
        capture_output=True,
        text=True,
        check=True,
    )
    assert completed.stdout == f"$(touch {marker})"
    assert not marker.exists()


def test_environment_exports_reject_invalid_variable_names():
    with pytest.raises(ValueError):
        slurm._render_env_exports({"X; touch malicious": "value"})


def test_local_conda_preserves_literal_command_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    captured: list[str] = []
    marker = tmp_path / "executed"
    monkeypatch.setattr(
        slurm, "launch_local_subprocess", lambda job_id, cmd, gpus: captured.extend(cmd)
    )
    slurm.submit_local_conda(
        log_dir=str(tmp_path / "logs"),
        cmd=["printf", "%s", f"$(touch {marker})"],
        time="00:10:00", partition="x", cpus=1, gpus=0, mem="1G"
    )
    subprocess.run(
        ["bash", "-c", "module(){ :; }; " + captured[2]],
        capture_output=True, check=True,
    )
    assert not marker.exists()
    assert (tmp_path / "logs/job_log.out").read_text() == f"$(touch {marker})"


def test_sbatch_rejects_newline_in_directive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        slurm.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, stdout="Submitted batch job 1\n", stderr=""),
    )
    with pytest.raises(ValueError, match="newline|directive"):
        slurm.submit_conda(
            log_dir=str(tmp_path), cmd=["python", "eval.py"],
            time="00:01:00", partition="gpu\nrm -rf -- /tmp/example", cpus=1,
            gpus=0, mem="1G",
        )


def test_local_scheduler_activation_does_not_execute_substitution(tmp_path: Path):
    from shinka.launch.scheduler import JobScheduler, LocalJobConfig

    marker = tmp_path / "executed"
    scheduler = JobScheduler(
        "local",
        LocalJobConfig(activate_script=f"$(touch {marker})"),
    )
    try:
        command = scheduler._build_command("candidate.py", str(tmp_path))
        subprocess.run(command, capture_output=True, check=False)
        assert not marker.exists()
    finally:
        scheduler.shutdown()


def test_scheduler_unavailable_status_does_not_spin_forever(monkeypatch):
    monkeypatch.setattr(slurm, "get_job_status", lambda job_id: None)
    with pytest.raises(RuntimeError, match="status"):
        slurm.monitor("1234", poll_interval=0, max_status_errors=3)


def test_queued_local_job_is_not_considered_complete(monkeypatch):
    monkeypatch.setitem(
        slurm.LOCAL_JOBS, "local-test-queued", {"popen": None, "status": "queued"}
    )
    assert slurm.get_job_status("local-test-queued") == "local-test-queued"


def test_cpu_only_local_slurm_job_skips_nvidia_smi(monkeypatch):
    import threading

    ready = threading.Event()
    launched = []

    def fake_run(*args, **kwargs):
        raise AssertionError("nvidia-smi must not be called for gpus=0")

    def fake_popen(cmd, env=None):
        launched.append((cmd, env))
        ready.set()
        return object()

    monkeypatch.setattr(slurm.subprocess, "run", fake_run)
    monkeypatch.setattr(slurm.subprocess, "Popen", fake_popen)
    slurm.launch_local_subprocess("local-test-cpu-only", ["python", "eval.py"], 0)
    assert ready.wait(timeout=1)
    assert launched[0][0] == ["python", "eval.py"]
    assert slurm.LOCAL_JOBS["local-test-cpu-only"]["status"] == "running"


@pytest.mark.parametrize("job_type", ["conda", "docker"])
def test_sbatch_tempfiles_are_deleted_after_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, job_type: str
):
    saved_paths = []

    def fake_submit(cmd, **kwargs):
        saved_paths.append(Path(cmd[1]))
        assert saved_paths[-1].exists()
        return subprocess.CompletedProcess(cmd, 0, stdout="Submitted batch job 55\n")

    monkeypatch.setattr(slurm.subprocess, "run", fake_submit)
    common = dict(log_dir=str(tmp_path), cmd=["python", "eval.py"], time="00:01:00",
                  partition="cpu", cpus=1, gpus=0, mem="1G")
    if job_type == "conda":
        slurm.submit_conda(**common)
    else:
        slurm.submit_docker(**common, docker_flags="", image="python:3.11", image_tar_path="/tmp/safe.tar")
    assert all(not path.exists() for path in saved_paths)


def test_sbatch_failure_does_not_log_full_script_or_keep_script(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
):
    saved_paths = []

    def fake_submit(cmd, **kwargs):
        saved_paths.append(Path(cmd[1]))
        raise subprocess.CalledProcessError(1, cmd, stderr="submission rejected")

    monkeypatch.setattr(slurm.subprocess, "run", fake_submit)
    with pytest.raises(subprocess.CalledProcessError):
        slurm.submit_conda(
            log_dir=str(tmp_path), cmd=["python", "eval.py"], time="00:01:00",
            partition="cpu", cpus=1, gpus=0, mem="1G",
            eval_env={"SENSITIVE_EXAMPLE": "do-not-print-this-example"},
        )
    assert all(not path.exists() for path in saved_paths)
    assert "do-not-print-this-example" not in caplog.text
