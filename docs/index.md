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

The v6 development snapshot now includes authenticated remote evaluation, durable leases, bounded workflow evolution and AST/IR optimization. See [v4.1–v6 operations and evidence](omega/EVOLUTION_V41_V6.md). The v9 snapshot adds bounded [formal verification, knowledge distillation and multilevel coevolution](omega/EVOLUTION_V7_V9.md). The v12 snapshot adds [recursive improvement, paired benchmarking and symbolic discovery](omega/EVOLUTION_V10_V12.md). All initial roadmap stages have bounded implementations; external validation and production hardening remain open.

## Imported foundation

The upstream authors' documentation is preserved in the [ShinkaEvolve guide](upstream_index.md). Its APIs and examples describe the imported runtime, not the canonical OMEGA-X interface. No upstream authorship, license or citations have been removed.
