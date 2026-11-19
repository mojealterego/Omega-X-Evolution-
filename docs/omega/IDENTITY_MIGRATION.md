# OMEGA-X namespace and packaging migration

Development identity: `omega-x-evolution` / `0.4.0.dev1`. This is a namespace migration of v4, not a claim of completed v4.1 remote scheduling or a published PyPI release.

## Canonical interface

```python
from omega_x_evolution.engine import Config, run
from omega_x_evolution.checkpoint import CheckpointStore
```

```sh
python -m omega_x_evolution --seed 5 --generations 5 --evaluation-processes 2
# Installed command:
omega-x-evolution --seed 5 --generations 5
```

The implementation files (engine, checkpoint, workers, provider adapter and CLI) have moved byte-for-byte to `omega_x_evolution/`. Legacy `shinka.omega.engine`, `checkpoint`, `workers` and `providers` imports resolve to the actual canonical module objects. There is no second engine. The old `shinka_omega` command and `python -m shinka.omega` remain supported. The offline canonical import does not import Shinka or load its dotenv files.

The upstream framework remains in `shinka/`; optional live proposals still use its client adapter. Distribution dependencies are unchanged for compatibility. Do not install the upstream and derivative distributions in the same environment: both contain the `shinka` package. Use a dedicated virtual environment. The canonical source-checkout offline engine needs only the Python standard library.

## Checkpoints

The existing checkpoint contract hashes engine.py, checkpoint.py and workers.py bytes, not their path. Their original Git blob IDs and Python patch-version checks are preserved. An actual pre-migration v4 checkpoint was created and then resumed by the new CLI on the same Python interpreter; its result was byte-identical to an uninterrupted run. Existing checkpoint constraints still apply: exact runtime bytes, Python patch version, configuration, key and benchmark. No v3 migration is introduced.

## Attribution and documentation

The original upstream README, index and license remain available. Package metadata names OMEGA-X Evolution as maintainer and retains Sakana AI as the original author. Project URLs and the MkDocs home point to OMEGA-X. No GitHub Actions workflow has been enabled.

## Verification

See [local evidence](verification-identity.txt). The targeted suite covers the existing worker pool, authenticated checkpoint and coevolution behavior plus import identity, CLI and migration contracts. The complete upstream distribution and the documentation-site build were not executed in the reconstructed checkout. No production deployment or remote cluster is claimed.
