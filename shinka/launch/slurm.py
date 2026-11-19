import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import threading
from shinka.utils import load_results
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


_SHELL_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SBATCH_FIELD_NAME = re.compile(r"[A-Za-z0-9_-]+\Z")


def _quote_command(argv: list[str]) -> str:
    """Render an argv vector without permitting shell interpolation."""
    return shlex.join([str(argument) for argument in argv])


def _quote_flags(flags: str) -> str:
    """Treat Docker flags as argv, not as a shell fragment."""
    return _quote_command(shlex.split(flags))


def _safe_sbatch_fields(**fields: object) -> None:
    """Prevent newline injection into batch directives and script headers."""
    for name, value in fields.items():
        if "\n" in str(value) or "\r" in str(value):
            raise ValueError(f"SBATCH directive {name} contains a newline")


def _safe_sbatch_params(params: dict[str, object]) -> str:
    lines = []
    for name, value in params.items():
        if not _SBATCH_FIELD_NAME.fullmatch(name):
            raise ValueError(f"Invalid SBATCH directive name: {name}")
        _safe_sbatch_fields(**{name: value})
        lines.append(f"#SBATCH --{name}={value}")
    return "\n".join(lines)


def _render_env_exports(
    eval_env: Optional[Dict[str, str]], separator: str = "\n"
) -> str:
    """Render environment variables as safely quoted shell assignments."""
    if not eval_env:
        return ""
    exports = []
    for key, value in eval_env.items():
        if not _SHELL_VARIABLE_NAME.fullmatch(key):
            raise ValueError(f"Invalid shell variable name: {key}")
        exports.append(f"export {key}={shlex.quote(str(value))}")
    return separator.join(exports)


def _render_env_docker_flags(eval_env: Optional[Dict[str, str]]) -> str:
    """Render safely quoted Docker -e options."""
    if not eval_env:
        return ""
    flags = []
    for key, value in eval_env.items():
        if not _SHELL_VARIABLE_NAME.fullmatch(key):
            raise ValueError(f"Invalid environment variable name: {key}")
        flags.append(f"-e {shlex.quote(f'{key}={value}')}")
    return " ".join(flags)


# Configuration for Docker image caching
DOCKER_CACHE_DIR = Path(os.path.expanduser("~/docker_cache"))
try:
    DOCKER_CACHE_DIR.mkdir(exist_ok=True)
except PermissionError:
    # This can happen if the module is imported in a restricted environment
    # (like a Docker container) where the user doesn't have a home directory
    # or write access to it. This is fine if we're not using the caching feature.
    pass
CACHE_MANIFEST = DOCKER_CACHE_DIR / "cache_manifest.json"

# track local jobs for status checks
LOCAL_JOBS: dict[str, dict] = {}


def _has_value(value: Optional[str]) -> bool:
    return value is not None and value.strip() != ""


def _escape_double_quotes(value: str) -> str:
    """Escape shell metacharacters while retaining existing double-quote format."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )


def _build_activation_commands(
    conda_env: Optional[str] = None,
    activate_script: Optional[str] = None,
    *,
    separator: str = "\n",
) -> str:
    if _has_value(conda_env) and _has_value(activate_script):
        raise ValueError("conda_env and activate_script are mutually exclusive")

    commands: list[str] = []
    if _has_value(activate_script):
        quoted_path = _escape_double_quotes(activate_script.strip())
        commands.extend(
            [
                f'echo "Activating sourced environment: {quoted_path}"',
                f'source "{quoted_path}"',
            ]
        )
    elif _has_value(conda_env):
        env_name = conda_env.strip()
        echo_name = _escape_double_quotes(env_name)
        commands.extend(
            [
                f'echo "Activating conda environment: {echo_name}"',
                "source $(conda info --base)/etc/profile.d/conda.sh",
                f"conda activate {shlex.quote(env_name)}",
            ]
        )
    return separator.join(commands)


def load_cache_manifest():
    """Load the cache manifest file."""
    if CACHE_MANIFEST.exists():
        with open(CACHE_MANIFEST, "r") as f:
            return json.load(f)
    return {}


def save_cache_manifest(manifest):
    """Save the cache manifest file."""
    with open(CACHE_MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2)


def get_local_image(image_name):
    """Check if image exists locally and return the appropriate image name."""
    manifest = load_cache_manifest()

    # Check if image is in manifest
    if image_name in manifest:
        local_path = DOCKER_CACHE_DIR / manifest[image_name]
        if local_path.exists():
            # Return original image name instead of local registry
            return image_name

    # Try to pull and cache the image
    try:
        logger.info(f"Pulling and caching {image_name}...")
        subprocess.run(["docker", "pull", image_name], check=True)

        # Save the image
        image_file = f"{image_name.replace('/', '_').replace(':', '_')}.tar"
        image_path = DOCKER_CACHE_DIR / image_file
        subprocess.run(
            ["docker", "save", image_name, "-o", str(image_path)], check=True
        )

        # Update manifest
        manifest[image_name] = image_file
        save_cache_manifest(manifest)

        return image_name
    except subprocess.CalledProcessError:
        logger.info(f"Warning: Could not pull {image_name}, using as is")
        return image_name


SBATCH_DOCKER_TEMPLATE = """\
#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --output={log_dir}/job_log.out
#SBATCH --error={log_dir}/job_log.err
#SBATCH --time={time}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --gres=gpu:{gpus}
{additional_sbatch_params}

# (optional) load modules or set env here
module --quiet purge

echo "Job running on $(hostname) under Slurm job $SLURM_JOB_ID"
echo "Launching Docker container…"

# Load image from tar if specified, otherwise pull from registry
{load_command}

docker run --rm \\
    {eval_env_docker_flags} \\
    {docker_flags} \\
    {image} {cmd}

exit $?
"""

SBATCH_CONDA_TEMPLATE = """\
#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --output={log_dir}/job_log.out
#SBATCH --error={log_dir}/job_log.err
#SBATCH --time={time}
#SBATCH --partition={partition}
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={cpus}
#SBATCH --gres=gpu:{gpus}
{additional_sbatch_params}

# Load modules
module --quiet purge
{module_load_commands}

echo "Job running on $(hostname) under Slurm job $SLURM_JOB_ID"

# Activate Python environment when configured
{activation_commands}

{eval_env_exports}
{cmd}

exit $?
"""


def submit_docker(
    log_dir: str,
    cmd: list[str],
    time: str,
    partition: str,
    cpus: int,
    gpus: int,
    mem: Optional[str],
    docker_flags: str,
    image: str,
    image_tar_path: Optional[str] = None,
    verbose: bool = False,
    eval_env: Optional[Dict[str, str]] = None,
    local: bool = False,
    **sbatch_kwargs,
):
    if local:
        return submit_local_docker(
            log_dir=log_dir,
            cmd=cmd,
            time=time,
            partition=partition,
            cpus=cpus,
            gpus=gpus,
            mem=mem,
            docker_flags=docker_flags,
            image=image,
            image_tar_path=image_tar_path,
            verbose=verbose,
            eval_env=eval_env,
            **sbatch_kwargs,
        )
    job_name = f"docker-{uuid.uuid4().hex[:6]}"
    _safe_sbatch_fields(log_dir=log_dir, time=time, partition=partition, image=image, mem=mem)
    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    load_command = ""
    if image_tar_path:
        tar_path = shlex.quote(image_tar_path)
        load_command = f"""
if [ -f {tar_path} ]; then
    echo "Loading Docker image from an archive..."
    docker load < {tar_path}
else
    echo "Image archive not found, exiting."
    exit 1
fi
"""
    else:
        # Fallback to existing pull/cache logic
        get_local_image(image)  # This function pulls and caches the image
        image_file = f"{image.replace('/', '_').replace(':', '_')}.tar"
        cached_file = shlex.quote(str(DOCKER_CACHE_DIR / image_file))
        quoted_image = shlex.quote(image)
        load_command = f"""
if [ -f {cached_file} ]; then
    echo "Loading cached image..."
    docker load < {cached_file}
    if ! docker image inspect {quoted_image} >/dev/null 2>&1; then
        echo "Failed to load cached image, pulling from registry..."
        docker pull {quoted_image}
    fi
else
    echo "Pulling image..."
    docker pull {quoted_image}
fi
"""

    if mem is not None:
        sbatch_kwargs["mem"] = mem

    additional_sbatch_params = _safe_sbatch_params(sbatch_kwargs)

    sbatch_script = SBATCH_DOCKER_TEMPLATE.format(
        job_name=job_name,
        log_dir=log_dir,
        time=time,
        partition=partition,
        cpus=cpus,
        gpus=gpus,
        additional_sbatch_params=additional_sbatch_params,
        docker_flags=_quote_flags(docker_flags),
        image=shlex.quote(image),
        cmd=_quote_command(cmd),
        load_command=load_command,
        eval_env_docker_flags=_render_env_docker_flags(eval_env),
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sbatch") as f:
        f.write(sbatch_script)
        sbatch_path = f.name

    try:
        result = subprocess.run(
            ["sbatch", sbatch_path], stdout=subprocess.PIPE, check=True, text=True
        )
    finally:
        Path(sbatch_path).unlink(missing_ok=True)
    # Slurm replies: "Submitted batch job <jobid>"
    job_id = result.stdout.strip().split()[-1]
    if verbose:
        logger.info(f"Submitted Docker job {job_id}")
    return job_id


def submit_conda(
    log_dir: str,
    cmd: list[str],
    time: str,
    partition: str,
    cpus: int,
    gpus: int,
    mem: Optional[str],
    conda_env: str = "",
    activate_script: Optional[str] = None,
    modules: Optional[list[str]] = None,
    verbose: bool = False,
    eval_env: Optional[Dict[str, str]] = None,
    local: bool = False,
    **sbatch_kwargs,
):
    if local:
        return submit_local_conda(
            log_dir=log_dir,
            cmd=cmd,
            time=time,
            partition=partition,
            cpus=cpus,
            gpus=gpus,
            mem=mem,
            conda_env=conda_env,
            activate_script=activate_script,
            modules=modules,
            verbose=verbose,
            eval_env=eval_env,
            **sbatch_kwargs,
        )
    job_name = f"conda-{uuid.uuid4().hex[:6]}"
    _safe_sbatch_fields(log_dir=log_dir, time=time, partition=partition, mem=mem)
    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)

    if modules is None:
        modules = []

    module_load_commands = "\n".join(
        f"module load {shlex.quote(module)}" for module in modules
    )
    activation_commands = _build_activation_commands(
        conda_env=conda_env,
        activate_script=activate_script,
    )

    if mem is not None:
        sbatch_kwargs["mem"] = mem

    additional_sbatch_params = _safe_sbatch_params(sbatch_kwargs)

    sbatch_script = SBATCH_CONDA_TEMPLATE.format(
        job_name=job_name,
        log_dir=log_dir,
        time=time,
        partition=partition,
        cpus=cpus,
        gpus=gpus,
        additional_sbatch_params=additional_sbatch_params,
        activation_commands=activation_commands,
        module_load_commands=module_load_commands,
        cmd=_quote_command(cmd),
        eval_env_exports=_render_env_exports(eval_env),
    )

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sbatch") as f:
        f.write(sbatch_script)
        sbatch_path = f.name

    try:
        result = subprocess.run(
            ["sbatch", sbatch_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        # Do not log the complete batch script: it may contain secrets.
        logger.warning("Unable to submit Conda job (exit=%s)", e.returncode)
        raise
    finally:
        Path(sbatch_path).unlink(missing_ok=True)

    # Slurm replies: "Submitted batch job <jobid>"
    job_id = result.stdout.strip().split()[-1]
    if verbose:
        logger.info(f"Submitted Conda job {job_id}")
    return job_id


def launch_local_subprocess(
    job_id: str,
    cmd: list[str],
    gpus: int,
):
    """Queue local execution without requiring NVIDIA tools for CPU jobs.

    Record queued, running, and failed states so a pending job is not
    mistaken for a successfully completed evaluation.
    """
    if gpus < 0:
        raise ValueError("gpus must be non-negative")
    LOCAL_JOBS[job_id] = {"popen": None, "status": "queued", "error": None}

    def runner():
        try:
            while True:
                environment = os.environ.copy()
                if gpus:
                    res = subprocess.run(
                        [
                            "nvidia-smi",
                            "--query-gpu=index,memory.used",
                            "--format=csv,noheader,nounits",
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=15,
                    )
                    free = []
                    for line in res.stdout.strip().splitlines():
                        idx, used = (part.strip() for part in line.split(",", 1))
                        if used == "0":
                            free.append(idx)
                    if len(free) < gpus:
                        time.sleep(5)
                        continue
                    # Never modify the global environment across concurrent jobs.
                    environment["CUDA_VISIBLE_DEVICES"] = ",".join(free[:gpus])
                proc = subprocess.Popen(cmd, env=environment)
                LOCAL_JOBS[job_id]["popen"] = proc
                LOCAL_JOBS[job_id]["status"] = "running"
                return
        except Exception as exc:
            LOCAL_JOBS[job_id]["status"] = "failed"
            LOCAL_JOBS[job_id]["error"] = str(exc)
            logger.exception("Failed to launch local job %s", job_id)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()


def submit_local_docker(
    log_dir: str,
    cmd: list[str],
    time: str,
    partition: str,
    cpus: int,
    gpus: int,
    mem: Optional[str],
    docker_flags: str,
    image: str,
    image_tar_path: Optional[str] = None,
    verbose: bool = False,
    eval_env: Optional[Dict[str, str]] = None,
    **kwargs,
) -> str:
    """Submit a job to run locally in a Docker container."""
    job_id = f"local-{uuid.uuid4().hex[:6]}"
    log_dir_path = Path(log_dir)
    os.makedirs(log_dir_path, exist_ok=True)
    image_name = get_local_image(image)
    image_file = f"{image.replace('/', '_').replace(':', '_')}.tar"
    docker_env_flags = _render_env_docker_flags(eval_env)
    # build bash command with logging
    full = (
        f"if [ -f {shlex.quote(str(DOCKER_CACHE_DIR / image_file))} ]; then "
        f"docker load < {shlex.quote(str(DOCKER_CACHE_DIR / image_file))}; "
        f"else docker pull {shlex.quote(image_name)}; fi; "
        f"docker run --rm {docker_env_flags} "
        f"{_quote_flags(docker_flags)} {shlex.quote(image_name)} "
        f"{_quote_command(cmd)} >> {shlex.quote(str(log_dir_path / 'job_log.out'))} "
        f"2>> {shlex.quote(str(log_dir_path / 'job_log.err'))}"
    )
    launch_local_subprocess(job_id, ["bash", "-lc", full], gpus)
    if verbose:
        logger.info(f"Submitted local Docker job {job_id}")
    return job_id


def submit_local_conda(
    log_dir: str,
    cmd: list[str],
    time: str,
    partition: str,
    cpus: int,
    gpus: int,
    mem: Optional[str],
    conda_env: str = "",
    activate_script: Optional[str] = None,
    modules: Optional[list[str]] = None,
    verbose: bool = False,
    eval_env: Optional[Dict[str, str]] = None,
    **kwargs,
) -> str:
    """Submit local conda job."""
    job_id = f"local-conda-{uuid.uuid4().hex[:6]}"
    log_dir = os.path.abspath(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    modules = modules or []
    loads = "; ".join(f"module load {shlex.quote(m)}" for m in modules)
    activation_commands = _build_activation_commands(
        conda_env=conda_env,
        activate_script=activate_script,
        separator="; ",
    )
    env_exports = _render_env_exports(eval_env, separator="; ")
    full_cmd = "; ".join(
        segment
        for segment in [
            "module --quiet purge",
            loads,
            activation_commands,
            env_exports,
            f"{_quote_command(cmd)} >> {shlex.quote(str(Path(log_dir) / 'job_log.out'))} "
            f"2>> {shlex.quote(str(Path(log_dir) / 'job_log.err'))}",
        ]
        if segment
    )
    launch_local_subprocess(job_id, ["bash", "-lc", full_cmd], gpus)
    if verbose:
        logger.info(f"Submitted local Conda job {job_id}")
    return job_id


def get_job_status(job_id: str) -> Optional[str]:
    """Return running/queued ID, empty string on completion, None on error."""
    if job_id.startswith("local-"):
        job = LOCAL_JOBS.get(job_id)
        if not job or job.get("status") == "failed":
            return None
        proc = job.get("popen")
        if proc is None:
            return job_id if job.get("status") == "queued" else None
        return job_id if proc.poll() is None else ""
    try:
        result = subprocess.run(
            ["squeue", "-j", str(job_id), "--noheader"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError) as exc:
        logger.warning("Unable to query SLURM job %s: %s", job_id, exc)
        return None


def monitor(
    job_id,
    results_dir=None,
    poll_interval=10,
    verbose: bool = False,
    max_status_errors: int = 5,
):
    """Wait for a job, failing closed after repeated scheduler errors.

    ``None`` is an unknown scheduler state, not successful completion.
    The retry bound prevents an infinite loop when squeue is unavailable.
    """
    if max_status_errors < 1:
        raise ValueError("max_status_errors must be positive")
    if poll_interval < 0:
        raise ValueError("poll_interval cannot be negative")
    failures = 0
    if verbose:
        logger.info("Monitoring job %s...", job_id)
    while True:
        status = get_job_status(job_id)
        if status == "":
            if verbose:
                logger.info("Job %s completed", job_id)
            break
        if status is None:
            failures += 1
            if failures >= max_status_errors:
                raise RuntimeError(
                    f"Unable to obtain job status for {job_id} "
                    f"after {failures} consecutive attempts"
                )
        else:
            failures = 0
        if verbose:
            logger.info("Job %s status: %s", job_id, status)
        time.sleep(poll_interval)
    if results_dir is not None:
        results = load_results(results_dir)
        local_job = LOCAL_JOBS.get(job_id)
        if local_job:
            process = local_job.get("popen")
            if process is not None and process.returncode != 0:
                results["correct"] = {"correct": False}
                results["metrics"] = {}
        return results
