#!/usr/bin/env python3
"""Run the targeted runtime hardening suite with minimal dependencies.

This isolated runner intentionally supplies only the two shinka.utils symbols
used by the local job modules. It is not a replacement for the project's full
integration suite, which requires installing all dependencies from pyproject.

Requires pytest and psutil. No LLM API keys, cloud accounts, SLURM or GPU.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


def main() -> int:
    try:
        import pytest
        import psutil  # noqa: F401 (required for process tree assertions)
    except ImportError as exc:
        print(f"Missing test dependency: {exc}. Install pytest and psutil.", file=sys.stderr)
        return 2

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    source = root / "shinka" / "utils" / "general.py"
    spec = importlib.util.spec_from_file_location("shinka_utils_general_test", source)
    assert spec is not None and spec.loader is not None
    general = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(general)

    # This process only: load the actual source, without importing the large
    # optional dependency graph through shinka.utils.__init__.
    module = types.ModuleType("shinka.utils")
    module.__path__ = [str(root / "shinka" / "utils")]
    module.parse_time_to_seconds = general.parse_time_to_seconds
    module.load_results = general.load_results
    sys.modules["shinka.utils"] = module
    sys.modules["shinka.utils.general"] = general

    test_files = [
        root / "tests" / "test_local_process_lifecycle.py",
        root / "tests" / "test_slurm_shell_safety.py",
        root / "tests" / "test_result_file_integrity.py",
        root / "tests" / "test_scheduler_env_activation.py",
    ]
    return pytest.main(["-q", *map(str, test_files)])


if __name__ == "__main__":
    sys.exit(main())
