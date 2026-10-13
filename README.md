# Governing Change in AI-Driven Development — Companion Code

[日本語のREADMEはこちら / Japanese README](README.ja.md)

This repository contains the **reproducible local exercises** for *Governing Change in AI-Driven Development*, First Edition (1.0.0), and its Japanese edition, *AI駆動開発の変更統治*. It **does not** contain the paid book chapters or book illustrations.

- Companion materials version: `1.0.0`. Repository: https://github.com/kanaria007/ai-change-governance-materials
- Materials ID: `ai-change-governance-materials-1.0.0`.
- Book listings: see [Book links / 書籍リンク](BOOK_LINKS.md). This bilingual navigation file is updated on the repository’s default branch; copies in tags or downloaded archives remain snapshots. It is not part of the verified teaching materials.
- License: the files in **this code repository** are released under the [MIT License](LICENSE). The book manuscripts and book illustrations are separate works and are not included here.

## What you can reproduce

| Model | Main file | What the exercise examines |
|---|---|---|
| Basic model | `lab/change_control.py` | Evidence freshness, counterexamples, and execution authority |
| Operation-scoped model | `lab/coverage_control.py` | Missing required checks, limited activation, and separation of candidate and active configurations |
| Discovery experiment | `lab/route_discovery.py` | Comparing ways to discover source-code routes, including missed paths and limits of applicability |

**Not production software.** The exercises do not invoke an actual AI model, merge Git branches, or deploy to an external system. The Python lab uses `exec()` on **trusted, bundled example code**. Never feed it an untrusted pull request or third-party code. The package does not provide sandboxing, a production admission controller, or protection for a real authorization system.

## Requirements and quick start

The bundled exercise results were generated using **Python 3.13.5 on Linux**. Running the exercises requires no third-party Python packages, API keys, or network access. At the repository root:

```bash
python --version
python verify_package.py
cd lab
python -m unittest -v
python run_experiments.py --output rerun-results.json
python run_expansion.py --output rerun-expansion.json
python runtime_scenarios.py
```

Use `python3` instead of `python` if your environment requires it. Run the commands from the indicated directory.

The companion materials include **107 unit tests for the teaching models**: 31 for the basic model, 37 for operation-scoped coverage, 16 for discovery, and 23 for the candidate/active runtime boundary. The CI evidence collector (8 tests) and package verifier (13 tests) have separate test suites. Passing these tests does not demonstrate a production defect-prevention rate.

### Verifying the edition cited by either book

Inspect `EDITION.json` for the edition ID. Both language editions cite the SHA-256 digest of `FILE-MANIFEST.json` in their appendix. To compare the package to the digest **printed in your edition**:

```bash
python verify_package.py --expected-manifest-sha256 sha256:<64-character-value-from-your-book>
```

Replace the placeholder argument with the complete `sha256:` value in the appendix. Without that option, the verifier checks the bundled manifest and detects omitted experiment files within its declared scope. It does not authenticate the publisher or verify unrelated files. Hashes establish content identity, not safety or provenance by themselves.

### Included results

| File | Contents |
|---|---|
| `lab/results.json` | Basic scenarios A–F, and exhaustive versus dependency-scoped reevaluation |
| `lab/expansion-results.json` | E1/E2 decisions, strategy selection/application, and discovery limits |
| `lab/runtime-boundary-results.json` | Holding an unverified candidate, retaining active code, and stopping calls on runtime mismatch |

Write new experiment results to `rerun-*.json` instead of overwriting the bundled observations. Environment and timestamp fields can differ even when the relevant scenarios agree.

## GitHub Actions and CI evidence

`.github/workflows/lab-checks.yml` defines checks for `pull_request`, `merge_group`, and pushes to `main`. It compares the package manifest, runs test suites, and records the checked-out Git revision and test inputs. See [the CI integration guide](examples/ci/README.md).

**The bundled evidence is from local execution; no GitHub Actions results are claimed here.** A `PASS` written by code from an untrusted PR must not automatically grant a privileged deployment. The model deliberately keeps evaluating the changed code separate from granting permission to act.

## Issues, support, and license

- Companion code and repository documentation are licensed under **MIT**. Preserve the copyright and license notices when redistributing.
- The paid Japanese/English manuscripts and the book's figures are **not part of this repository** and are not relicensed under MIT.
- Reproducible companion bugs can be reported through [GitHub Issues](https://github.com/kanaria007/ai-change-governance-materials/issues), if Issues are enabled. Include platform, Python version, commands, expected/actual behavior, and a minimal reproduction. Read [CONTRIBUTING.md](CONTRIBUTING.md).
- Individual consulting, production integration, private reviews, and guaranteed response times are **not included**.
- Do not post credentials, proprietary code, customer data, or private logs in Issues.

## Limits of this implementation

The operation-scoped model keeps candidate changes from silently replacing approved active code. If the observed runtime no longer matches the approved configuration—or cannot be observed—the local simulated call is blocked. External authorization systems, crash-durable operation records, live GitHub approval gates, and restoration in a real deployment environment are beyond the implementation.

The scenarios, expected outcomes, evaluators, and synthetic source examples were designed in the same process. Reproducing these results is not independent evidence of generalization to unseen repositories or improved delivery performance.

## Fixed materials and current book links

The book pins `FILE-MANIFEST.json` to identify reproducible exercise code, test cases, fixture sources, evaluation plans, and recorded results. It intentionally **does not hash README files, guides, LICENSE, CI workflow configuration, or `BOOK_LINKS.md`**. Editorial corrections and store-link updates therefore do not require a new experiment manifest or a new book binding. Changes to the tracked experimental sources, plans, or results do.

For current store URLs, open the repository’s **default branch** and read `BOOK_LINKS.md`. A copy inside a tag, Release asset, or downloaded ZIP does not update when the default branch changes. Keep the published `v1.0.0` tag and its Release assets unchanged. The repository’s About field may point to the same navigation page, but it is not a separate source of release settings.
