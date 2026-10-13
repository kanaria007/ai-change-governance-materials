"""Record a trusted lab test run against an observed Git checkout.

This is a CI wiring example, not an authenticated attestation or deployment gate.
The tested repository and this script run in the same trust domain. Never use
this self-reported JSON alone to authorize an untrusted PR's production effect.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


def digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   text=True, stderr=subprocess.PIPE).strip()


def source_hashes(root: Path) -> dict[str, str]:
    paths = sorted((root / "lab").rglob("*.py"))
    paths += [root / "lab/experiment_plan.json", root / "examples/ci/collect_lab_result.py"]
    if not paths or any(not p.is_file() for p in paths):
        raise ValueError("required lab inputs are missing")
    if any(p.is_symlink() for p in paths):
        raise ValueError("symlink inputs are outside this example's checkout model")
    return {str(p.relative_to(root)): digest(p.read_bytes()) for p in paths}


def classify(return_code: int, log: str, stable: bool) -> tuple[str, int, str]:
    counts = re.findall(r"^Ran (\d+) tests? in ", log, re.MULTILINE)
    count = int(counts[-1]) if counts else 0
    if not stable:
        return "ERROR", count, "checkout_or_inputs_changed"
    if not count:
        return "ERROR", 0, "no_completed_test_summary"
    if return_code != 0:
        return "FAIL", count, "unittest_did_not_pass"
    if not re.search(r"^OK(?:\s|$)", log, re.MULTILINE):
        return "ERROR", count, "success_summary_missing"
    return "PASS", count, "declared_lab_tests_passed"


def collect(root: Path, output: Path) -> int:
    root = root.resolve()
    if Path(git(root, "rev-parse", "--show-toplevel")).resolve() != root:
        raise ValueError("run against the repository root")
    revision = git(root, "rev-parse", "--verify", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision):
        raise ValueError("invalid observed Git revision")
    expected = os.environ.get("GITHUB_SHA")
    if expected and expected != revision:
        raise ValueError("checked-out HEAD differs from the event revision")
    # Include untracked Python files in the content record; do not silently
    # attribute a dirty tracked checkout to its HEAD commit.
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("tracked checkout is dirty")
    before = source_hashes(root)
    command = [sys.executable, "-m", "unittest", "discover", "-s", "lab", "-v"]
    process = subprocess.run(command, cwd=root, text=True, capture_output=True,
                             timeout=120, check=False)
    log = process.stdout + process.stderr
    after = source_hashes(root)
    stable = (before == after and revision == git(root, "rev-parse", "--verify", "HEAD")
              and not git(root, "status", "--porcelain", "--untracked-files=no"))
    outcome, count, reason = classify(process.returncode, log, stable)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "unittest.log").write_text(log, encoding="utf-8")
    report = {
        "schema": "ci-lab-run/v1", "observed_source_revision": revision,
        "event": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "command": command, "python": platform.python_version(),
        "outcome": outcome, "tests_ran": count, "reason": reason,
        "inputs_stable_during_run": bool(stable),
        "source_hashes": before, "log_ref": digest(log.encode("utf-8")),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "tested_scope": "the book's local lab unit tests, not application or release acceptance",
        "authenticated_attestation": False,
        "production_authorization": False,
    }
    (output / "ci-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n",
                                            encoding="utf-8")
    print(f"{outcome}: {count} tests; observed revision {revision}")
    return 0 if outcome == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("ci-results"))
    args = parser.parse_args()
    try:
        return collect(args.root, args.output)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
