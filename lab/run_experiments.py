"""Write measured teaching-model outputs, with no claims about real AI models."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from scenarios import scenario_results, compare_revalidation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("results.json"))
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    source_hashes = {p.name: "sha256:" + sha256(p.read_bytes()).hexdigest()
                     for p in sorted(here.glob("*.py"))}
    result = {
        "schema": "change-control-lab-results/v1",
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": sys.version, "platform": platform.platform()},
        "source_hashes": source_hashes,
        "scope": "author-designed local deterministic teaching scenarios",
        "actual_ai_calls": 0,
        "actual_git_merges": 0,
        "actual_remote_deployments": 0,
        "scenario_results": scenario_results(),
        "revalidation_comparison": compare_revalidation(),
        "limitations": [
            "No independent holdout data or production traffic",
            "Fixtures, expected labels, dependency map and evaluator share authorship",
            "No model quality, real PR acceptance or workflow ROI measurement",
            "An undeclared batch route is intentionally missed by the original claim set",
            "Locks protect only a local simulated deployment pointer",
            "No durable deduplication, signature validation or distributed authorization",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
