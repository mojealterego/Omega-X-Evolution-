# OMEGA-X Evolution Ω

![OMEGA-X emblem](media/omega-x.svg)

**Autonomous Evolutionary Intelligence & Scientific Discovery Engine**

OMEGA-X is a separately maintained evolutionary research system, built upon the open-source ShinkaEvolve foundation and informed by AlphaEvolve and the Darwin Gödel Machine. Its current offline engine explores bounded numerical expressions using fixed validation, Pareto island archives, authenticated checkpoints and local multiprocessing. It does not execute unrestricted candidate Python.

## OMEGA-X documentation

- [Identity and packaging migration](omega/IDENTITY_MIGRATION.md)
- [Evolution engine and experimental limits](OMEGA_COEVOLUTION.md)
- [Runtime hardening](OMEGA_HARDENING.md)
- [Research traceability](omega/RESEARCH_TRACEABILITY_v4.md)

Start a local source-checkout experiment:

```sh
python -m omega_x_evolution --seed 5 --generations 5 --evaluation-processes 2
```

Remote execution is not implemented by the identity migration. The next engineering increment is the multi-host evaluation protocol and lease fencing.

## Imported foundation

The upstream authors' documentation is preserved in the [ShinkaEvolve guide](upstream_index.md). Its APIs and examples describe the imported runtime, not the canonical OMEGA-X interface. No upstream authorship, license or citations have been removed.
