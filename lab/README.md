# Running the Models and Reading the Results

[日本語 / Japanese](README.ja.md)

From this directory, run `python -m unittest -v` for the 107 model unit tests. Setup, the edition digest, and the CI example are documented in the repository's top-level [README](../README.md) and the book's appendix.

## Where to start

| Question | Run or inspect |
|---|---|
| What happens when evidence becomes stale? | `python run_experiments.py --output rerun-results.json` |
| How do E1's missing checks and limited activation lead to E2's new investigation? | `python coverage_scenarios.py` |
| How do discovery strategies compare and transfer to another synthetic case? | `python run_expansion.py --output rerun-expansion.json` |
| Can an unverified candidate silently become the active version? | `python runtime_scenarios.py` |

Basic scenario E has a missing claim covering a batch route. The result key `E_undeclared_batch_route` means the claim was undeclared, not that the existence of the route was unknown. E1 and E2 have separate lifecycle rows in `expansion-results.json`.

## Candidate versus active configuration

`ScopedController.observe_candidate()`—and its backward-compatible alias `observe()`—update only the **candidate**. `revalidate()` does not change the active code. When `execute()` rechecks current conditions and succeeds, it updates `active_snapshot` and the application generation.

`observe_runtime()` records a reported observation of the running environment. It neither loads nor authorizes the reported code. A mismatch or unknown runtime state blocks affected simulated calls. Updates to runtime observations require a monotonically increasing `epoch`.

## Experimenting with changes

If you edit discovery fixture sources, register the edited inputs as a separate experiment in `experiment_plan.json`. Use copies of the original fixtures to keep the packaged results reproducible.

If you encounter a `ModuleNotFoundError`, first check that your working directory is `lab/`. The error `fixture differs from declared plan` indicates a mismatch between fixture content and the identifier stored in the experimental plan.

The lab's `exec()` calls apply **only to trusted bundled code**. They do not isolate untrusted PRs.
