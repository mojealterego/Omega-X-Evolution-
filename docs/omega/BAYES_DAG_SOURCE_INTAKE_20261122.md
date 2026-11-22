# OMEGA-X — W10/W11/W14: Bayesian DAG structural gate (2026-11-22)

## Scope and primary sources

- `W10.PDF` — 33-page lecture *Sieci Rekurencyjne* by Nguyen Hung Son. Pages 13–20 discuss classical binary Hopfield energy, symmetric weights, and asynchronous/synchronous dynamics; pages 24–32 introduce Kohonen SOM. The existing OMEGA-X `holographic.py` already implements **bounded modern Hopfield-like association**, not the classical binary network; no duplicate Hopfield engine was added. Monotonic energy of the classical binary Hopfield network is specific to appropriate asynchronous single-neuron updates with symmetric, zero-diagonal weights, not arbitrary synchronous schedules.
- `W11.PDF` — 59 physical PDF pages (incremental slides, printed slide count 24) of *SVM: Maszyny Wektorów Podpierających*. Covers hard/soft margins, dual QP, KKT and kernel trick; not an imperative to reimplement existing NumPy/scikit-learn optimizers. No SVM trainer was added.
- `W14.PDF` — 26 pages of *Sieci Bayesowskie* (May 30, 2017). Pages 4–15 describe conditional independence, Bayesian DAGs and d-separation; pages 17–20 describe belief propagation and its polytree limit; pages 22–26 cover estimation assumptions. This source is the foundation of the new structural validator.

## Repository gap addressed

The existing `ontos_v57_causal_metrics.py` explicitly requires caller-provided *interventional* channels and does not identify observational causal effects. `graph_memory.py` is an authenticated provenance graph, and `holographic.py` is bounded associative trajectory retrieval; neither computes Bayesian d-separation. The new `ontos_bayesian_dag.py` is a **non-authorizing, standalone diagnostic** complementing those modules.

## Mathematical contract

Given a trusted acyclic DAG G=(V,E), sets X, Y, Z that are pairwise disjoint, the predicate `d_separated(X, Y, observed=Z)` decides whether all trails between X and Y are blocked by Z. It uses the **ancestral moral graph criterion**:

1. Compute the ancestors of X union Y union Z (including seeds).
2. Take the induced ancestral DAG and moralize it: undirect edges and connect co-parents.
3. Remove conditioned vertices Z.
4. Return separated if no X–Y path remains.

This handles colliders and conditioned descendants without mistaking graph traversal reachability for conditional dependence. Algorithm is iterative with explicit caps of 128 nodes and 2048 parent edges; moralization cost is bounded by `O(V+E+sum(deg_in^2))`. Nodes and parent lists have strict validation; cycles, unknown parents, duplicate parents and invalid labels fail closed. A canonical SHA-256 digest identifies a graph description; it **does not authenticate the scientific truth** of its assumptions.

The optional `selection_criterion(Y,S,given=X)` checks the *graphical* sufficient condition `Y independent S | X`. Under a credible Markov graph, positive selection probability at each supported X, and the usual observational-data assumptions, this implies `P(Y|X,S=1)=P(Y|X)` in regions of support. When the condition fails, this test reports `CRITERION_NOT_ESTABLISHED`; it does **not** prove that recovery is impossible by other data-fusion methods. **Neither result establishes an interventional `P(Y|do(X))` or validates the graph.** All reports have `assumptions_attested=false`, `release_authorized=false`.

## Verification and limitations

- `OMEGA-CAUSAL-001..012`, including 250 seeded random DAG cases independently checked by enumerating all simple trails and collider descendants.
- RED: focused test import failed because the module was not yet present.
- GREEN: 24 collected test instances PASS with 100% statement+branch coverage of the new module under Python 3.13.5 / pytest 9.0.2 / coverage 7.13.3.
- Compileall PASS.
- No runtime/engine promotion path modified. Existing GATE-09 statuses unchanged.
- NOT VERIFIED: full repository regression, real observed data, positivity assumptions, latent confounding, production causal identification, or benchmark speedups.

## Research classification

Source PDFs are treated as mathematical references, not requirements that expand mandatory ONTOS scope or warrant claims of new ML quality. The validator is bounded inference **about a proposed graph**, not inference that the proposed graph is correct.
