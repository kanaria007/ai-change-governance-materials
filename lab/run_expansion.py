"""Freeze development choice, then evaluate application/limits without retuning."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys

from coverage_scenarios import run_lifecycle, compare_coverage
from route_discovery import STRATEGIES, compare, probe, scan


def digest(path):
    return "sha256:" + sha256(path.read_bytes()).hexdigest()


def totals(rows):
    keys = ("tp", "fp", "fn", "tn", "candidate_count", "unresolved_count",
            "source_bytes", "ast_nodes", "edges_examined")
    return {k: sum(row[k] for row in rows) for k in keys}


def evaluate_set(root, name):
    per_strategy = {s: [] for s in STRATEGIES}
    golds = {}
    paths = sorted((root / "discovery_fixtures" / name).glob("*.py"))
    if not paths:
        raise ValueError("evaluation set is empty: " + name)
    for path in paths:
        source = path.read_text()
        gold = probe(source)
        golds[path.name] = gold
        for method in STRATEGIES:
            row = compare(source, method, gold)
            row["fixture"] = path.name
            per_strategy[method].append(row)
    return {"details": per_strategy, "totals": {s: totals(rs) for s, rs in per_strategy.items()},
            "observed_gold": golds}


def select_strategy(development):
    scores = development["totals"]
    return min(scores, key=lambda s: (scores[s]["fn"], scores[s]["fp"],
                                     scores[s]["edges_examined"], s))


def run(root):
    plan_path = root / "experiment_plan.json"
    plan = json.loads(plan_path.read_text())
    for rel, expected in plan["fixtures"].items():
        if digest(root / "discovery_fixtures" / rel) != expected:
            raise ValueError("fixture differs from declared plan: " + rel)
    # The selection function can see DEVELOPMENT ONLY. Application/limits are
    # executed afterwards; all authored artifacts remain same-author evidence.
    development = evaluate_set(root, "development")
    selected = select_strategy(development)
    choice = {"strategy": selected, "selected_from": "development only",
              "plan_ref": digest(plan_path),
              "status": "scoped_candidate_not_production_authorization",
              "scope": plan["adoption_scope"], "unresolved_rule": plan["unresolved_rule"],
              "retune_on_application": False}
    application = evaluate_set(root, "application")
    limits = evaluate_set(root, "limits")
    applied_rule = []
    for group in ("application", "limits"):
        for path in sorted((root / "discovery_fixtures" / group).glob("*.py")):
            discovery = scan(path.read_text(), selected)
            applied_rule.append({"fixture": str(path.relative_to(root)),
                "strategy": selected, "candidate_entries": list(discovery.candidates),
                "unresolved_entries": list(discovery.unresolved),
                "next_action": "investigation_required" if discovery.unresolved or discovery.parse_error
                               else "review_candidate_scope",
                "automatic_inventory_closure": False})
    failure_trace = {
        "id": "name-frame-missed-nightly",
        "observation": "development/d1.py nightly emits the declared document but name search omits it",
        "prior_frame": "entrypoint name contains export/csv/download",
        "failed_assumption": "all relevant routes expose feature vocabulary in their names",
        "alternative_frames": ["names plus callers", "reverse calls from an external-output primitive", "all entrypoints"],
        "selected_rule": choice,
        "lineage": {"source": "development/d1.py", "outcome_file": "expansion-results.json"},
        "known_limits": ["dynamic calls", "unregistered output primitives", "no dataflow sensitivity", "entrypoint inventory is bounded"],
        "rollback_condition": "unresolved routes or unacceptable extra review: suspend automatic closure, inspect all relevant entries or collect a different observation",
        "automatic_production_rule_update": False,
    }
    hashes = {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*.py"))}
    return {"schema": "change-control-expansion-results/v2", "run_at_utc": datetime.now(timezone.utc).isoformat(),
            "environment": {"python": sys.version, "platform": platform.platform()},
            "source_hashes": hashes, "plan_ref": digest(plan_path),
            "actual_ai_calls": 0, "actual_git_merges": 0, "actual_remote_deployments": 0,
            "lifecycle": run_lifecycle(), "coverage_comparison": compare_coverage(), "development": development,
            "frozen_choice": choice, "application": application, "limits": limits,
            "failure_trace": failure_trace, "applied_rule": applied_rule,
            "non_claims": ["not independent or blinded holdout evidence", "not a universal static analyzer", "not autonomous semantic rule invention",
                           "no measured savings in time, tokens or money", "no proof of complete real-world route discovery"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("expansion-results.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    result = run(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Selected on development:", result["frozen_choice"]["strategy"])
    for name in ("development", "application", "limits"):
        print(name)
        for strategy, counts in result[name]["totals"].items():
            print(" ", strategy, counts)
    print("E1/E2 lifecycle:", [(r["step"], r["verdict"]) for r in result["lifecycle"]["rows"]])
    print("Local scope enforcement:", result["lifecycle"]["local_boundary_probe"])


if __name__ == "__main__":
    main()
