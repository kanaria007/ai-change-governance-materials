"""Candidate/runtime separation, followed by a bounded runtime-observation check."""
from dataclasses import replace
import json
from coverage_scenarios import API_ONLY, initial_controller
from scenarios import APP_BAD, APP_V1


def run_runtime_boundary() -> dict:
    c = initial_controller()
    c.revalidate(API_ONLY)
    decision = c.decide(API_ONLY)
    first = c.execute(decision, "first-release")
    active = c.active_snapshot
    actor = {"role": "manager", "tenant": "tenant-a"}
    other = {"tenant": "tenant-b"}
    own = {"tenant": "tenant-a"}
    before = c.invoke_demo_route("api", actor, other)
    c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": APP_BAD}))
    pending = c.decide(API_ONLY)
    after = c.invoke_demo_route("api", actor, other)
    preserved = c.active_snapshot.fingerprint == active.fingerprint
    c.revalidate(API_ONLY)
    contradicted = c.decide(API_ONLY).verdict
    # The code is known to differ but remains compatible with the test contract.
    revised = active.with_changes(**{"app.py": APP_V1 + "\n# admitted revision\n"})
    c.observe_candidate(revised)
    c.revalidate(API_ONLY)
    prior_to_apply = c.active_snapshot.fingerprint
    applied = c.execute(c.decide(API_ONLY), "second-release")
    admitted_observation = c.runtime_observation
    unexpected_ref = revised.with_changes(**{"app.py": APP_BAD}).fingerprint
    c.observe_runtime(replace(admitted_observation, epoch=admitted_observation.epoch + 1,
                              snapshot_ref=unexpected_ref))
    contained = c.invoke_demo_route("api", actor, own)
    mismatch = c.decide(API_ONLY).reasons
    c.observe_runtime(replace(admitted_observation, epoch=c.runtime_observation.epoch + 1))
    restored = c.invoke_demo_route("api", actor, own)
    return {
        "schema": "runtime-boundary-demonstration/v1",
        "initial_activation": first["status"],
        "cross_tenant_before": before,
        "unverified_candidate_verdict": pending.verdict,
        "cross_tenant_after_candidate_observation": after,
        "active_preserved": preserved,
        "candidate_after_revalidation": contradicted,
        "revalidation_did_not_publish": prior_to_apply == active.fingerprint,
        "new_activation": applied["status"],
        "active_matches_admitted_candidate": c.active_snapshot.fingerprint == revised.fingerprint,
        "runtime_mismatch_call_allowed": contained,
        "runtime_mismatch_reasons": list(mismatch),
        "matching_reobservation_call_allowed": restored,
        "release_generation": c.release_generation,
        "runtime_history": c.runtime_history,
        "remote_runtime_observed": False,
        "scope": "trusted single-process teaching gateway; no remote recovery guarantee",
    }


if __name__ == "__main__":
    print(json.dumps(run_runtime_boundary(), ensure_ascii=False, indent=2))
