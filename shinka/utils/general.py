import json
from pathlib import Path
import logging
from typing import Optional
import yaml

logger = logging.getLogger(__name__)


def truncate_log_tail(text: str, max_chars: Optional[int] = None) -> str:
    """Return only the last ``max_chars`` characters of ``text``.

    Tail-biased because the end of a captured log holds the final results /
    error context. ``max_chars`` of None or <= 0 returns ``text`` unchanged. On
    truncation, a one-line marker noting how many characters were dropped is
    prepended so consumers can tell the log is partial.
    """
    if not text or max_chars is None or max_chars <= 0:
        return text
    if len(text) <= max_chars:
        return text
    dropped = len(text) - max_chars
    marker = f"... [truncated {dropped} chars of stdout; full log on disk] ...\n"
    return marker + text[-max_chars:]


def load_configs_from_yaml(config_path: str):
    """
    Loads configs from a YAML file.
    """
    from shinka.core import EvolutionConfig
    from shinka.database import DatabaseConfig

    with open(config_path, "r") as f:
        configs = yaml.safe_load(f)

    assert "db_config" in configs, "db_config not found in config file"
    assert "evo_config" in configs, "evo_config not found in config file"

    db_cfg = DatabaseConfig(**configs["db_config"])
    evo_cfg = EvolutionConfig(**configs["evo_config"])
    return evo_cfg, db_cfg


_DEFAULT_LOG_LOAD_BYTES = 4 * 1024 * 1024
_DEFAULT_JSON_LOAD_BYTES = 8 * 1024 * 1024


def _read_log_tail(path: Path, max_bytes: Optional[int]) -> str:
    """Load a tail of a potentially unbounded log without reading it all."""
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        length = handle.tell()
        if max_bytes is None or max_bytes < 0:
            start = 0
        else:
            start = max(0, length - max_bytes)
        handle.seek(start)
        output = handle.read().decode("utf-8", errors="replace")
    if start:
        return f"... [skipped {start} earlier log bytes; see file on disk] ...\n" + output
    return output


def _read_bounded_json(path: Path, max_bytes: int) -> object:
    """Parse an evaluation result with a strict byte budget."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            logger.warning("Rejecting oversized evaluation JSON: %s", path)
            return None
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        logger.warning("Rejecting invalid evaluation JSON %s: %s", path, exc)
        return None


def load_results(
    results_dir: str,
    max_log_bytes: Optional[int] = _DEFAULT_LOG_LOAD_BYTES,
    max_json_bytes: int = _DEFAULT_JSON_LOAD_BYTES,
):
    """Load and validate evaluation outputs without trusting generated JSON.

    Logs remain complete on disk. Only a bounded UTF-8 tail is returned to
    avoid exhausting orchestration memory when generated code floods stdout.
    Structured JSON must be an object and fit within the configured cap.
    """
    if max_json_bytes <= 0:
        raise ValueError("max_json_bytes must be positive")
    results = {"correct": {"correct": False}, "metrics": {}}
    directory = Path(results_dir)
    results["stdout_log"] = _read_log_tail(directory / "job_log.out", max_log_bytes)
    results["stderr_log"] = _read_log_tail(directory / "job_log.err", max_log_bytes)

    metrics_path = directory / "metrics.json"
    if metrics_path.exists():
        metrics = _read_bounded_json(metrics_path, max_json_bytes)
        if isinstance(metrics, dict):
            results["metrics"] = metrics
        else:
            logger.warning("Invalid metrics object at %s", metrics_path)
    else:
        logger.warning("Metrics file not found at %s", metrics_path)

    correct_path = directory / "correct.json"
    if correct_path.exists():
        correct = _read_bounded_json(correct_path, max_json_bytes)
        if isinstance(correct, dict) and type(correct.get("correct")) is bool:
            results["correct"] = correct
        else:
            logger.warning("Invalid correctness object at %s", correct_path)
    return results


def parse_time_to_seconds(time_str: str) -> int:
    """Converts hh:mm:ss to seconds."""
    parts = time_str.split(":") if isinstance(time_str, str) else []
    if len(parts) != 3 or any(not p.isascii() or not p.isdecimal() for p in parts):
        raise ValueError("Time format must be non-negative hh:mm:ss")
    h, m, s = (int(p) for p in parts)
    if m > 59 or s > 59:
        raise ValueError("Minutes and seconds must be between 0 and 59")
    return h * 3600 + m * 60 + s
