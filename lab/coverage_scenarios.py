"""E1 (known gap), E2 (inventory gap), and one trace of scoped activation."""
from __future__ import annotations
from dataclasses import replace
import inspect
from pathlib import Path

from change_control import CHECKERS, Claim, Controller
from coverage_control import (CoverageBinding, CoveragePolicy, RouteSpec, RouteView,
                              ScopedController, ScopedOperation)
from scenarios import base, CLAIMS, BATCH_CLAIM, BATCH_BAD, BATCH_GOOD
from route_discovery import probe, scan

API_ONLY = ScopedOperation(("api",))
ALL_KNOWN = ScopedOperation(("api", "batch"))
ROUTES = (RouteSpec("api", ("tenant", "wire", "storage")),
          RouteSpec("batch", ("tenant", "storage")))
APPROVED_SCOPES = {
    "tenant-v1": (("api", "tenant"),),
    "wire-v1": (("api", "wire"),),
    "storage-v1": (("api", "storage"), ("batch", "storage")),
    "batch-v1": (("batch", "tenant"),),
    "repo-api-v2": (("api", "tenant"),),
    "repo-batch-v2": (("batch", "tenant"),),
    "repo-delivery-v2": (("delivery", "tenant"),),
}


def binding(route: str, condition: str, claim: Claim) -> CoverageBinding:
    return CoverageBinding(route, condition, claim.id, claim.ref)


def initial_policy() -> CoveragePolicy:
    return CoveragePolicy(1, ROUTES, (
        binding("api", "tenant", CLAIMS[0]), binding("api", "wire", CLAIMS[1]),
        binding("api", "storage", CLAIMS[2]), binding("batch", "storage", CLAIMS[2])))


def initial_controller() -> ScopedController:
    return ScopedController(base().with_changes(**{"batch.py": BATCH_BAD}), CLAIMS,
                            initial_policy(), RouteView(1, (("api", False), ("batch", False))),
                            APPROVED_SCOPES)


def _repo_result(snapshot, entry: str):
    expected_helper = inspect.getsource(probe) + inspect.getsource(_repo_result)
    if snapshot.read("repo_probe_source.py") != expected_helper:
        raise ValueError("fixture helper identity does not match executed helper")
    result = probe(snapshot.read("document_routes.py"))
    if entry not in result["details"]:
        raise ValueError("entrypoint not observed")
    detail = result["details"][entry]
    if not detail["emits_declared_document"]:
        return False, "expected positive output was not observed"
    if detail["violations"]:
        return False, "tenant boundary counterexample: " + entry
    return True, "declared actor/tenant inputs passed: " + entry


def check_repo_api(snapshot):
    return _repo_result(snapshot, "export_csv")


def check_repo_batch(snapshot):
    return _repo_result(snapshot, "batch_export")


def check_repo_delivery(snapshot):
    return _repo_result(snapshot, "scheduled_delivery")


CHECKERS.update({"repo-api-v2": check_repo_api, "repo-batch-v2": check_repo_batch,
                 "repo-delivery-v2": check_repo_delivery})
REPO_API = Claim("repo-api-isolation", "declared repo API actor/tenant inputs",
                 ("document_routes.py", "repo_probe_source.py"), "repo-api-v2")
REPO_BATCH = Claim("repo-batch-isolation", "declared repo batch actor/tenant inputs",
                   ("document_routes.py", "repo_probe_source.py"), "repo-batch-v2")
REPO_DELIVERY = Claim("repo-delivery-isolation", "declared scheduled delivery actor/tenant inputs",
                      ("document_routes.py", "repo_probe_source.py"), "repo-delivery-v2")


def run_lifecycle() -> dict:
    c = initial_controller()
    rows: list[dict] = []
    def record(step, op=ALL_KNOWN, **extra):
        d = c.decide(op)
        rows.append({"step": step, "verdict": d.verdict, "reasons": list(d.reasons),
            "requested_routes": list(op.enabled_routes), "required_pairs": len(d.required),
            "mapped_pairs": len(d.covered), "route_epoch": c.view.epoch,
            "policy_revision": c.policy.revision, "checker_invocations_total": c.core.check_runs,
            "claim_states": {a.claim_id: a.status for a in d.assessments}, **extra})
    c.revalidate(API_ONLY)
    legacy = Controller(c.core.snapshot, CLAIMS); legacy.revalidate()
    record("E1_declared_batch_without_check", legacy_verdict=legacy.decide().verdict)
    record("E1_api_only_disabled_batch", API_ONLY)
    limited = c.execute(c.decide(API_ONLY), "limited-activation")
    same = {"role": "manager", "tenant": "tenant-a"}
    row = {"tenant": "tenant-a"}
    enforcement = {"api_allowed": c.invoke_demo_route("api", same, row),
                   "batch_allowed": c.invoke_demo_route("batch", same, row)}
    p2 = replace(c.policy, revision=2, bindings=c.policy.bindings +
                 (binding("batch", "tenant", BATCH_CLAIM),))
    c.update_policy(p2, CLAIMS + (BATCH_CLAIM,))
    record("E1_mapping_added_evidence_missing")
    c.revalidate(ALL_KNOWN)
    record("E1_batch_counterexample")
    c.observe(c.core.snapshot.with_changes(**{"batch.py": BATCH_GOOD}))
    record("E1_code_fixed_evidence_stale")
    c.revalidate(ALL_KNOWN)
    record("E1_revalidated_full_scope")
    full = c.execute(c.decide(ALL_KNOWN), "full-activation")
    record("E1_full_activation_applied")

    # E2 uses ACTUAL parseable source, not a prefilled call-graph fixture. All
    # known entrypoint tenant claims are rebound to this source before scanning.
    source = (Path(__file__).parent / "sample_repository/document_routes.py").read_text()
    snapshot = c.core.snapshot.with_changes(**{"document_routes.py": source,
        "repo_probe_source.py": inspect.getsource(probe) + inspect.getsource(_repo_result)})
    c.observe(snapshot)
    p3 = CoveragePolicy(3, ROUTES, (
        binding("api", "tenant", REPO_API), binding("api", "wire", CLAIMS[1]),
        binding("api", "storage", CLAIMS[2]), binding("batch", "storage", CLAIMS[2]),
        binding("batch", "tenant", REPO_BATCH)))
    c.update_policy(p3, (REPO_API, REPO_BATCH, CLAIMS[1], CLAIMS[2]))
    c.revalidate(ALL_KNOWN)
    record("E2_inventory_missing_scheduled_delivery")
    named, structural = scan(source, "name"), scan(source, "effect")
    registered_entries = {"export_csv", "batch_export"}
    additions = sorted(set(structural.candidates) - registered_entries)
    c.update_policy(replace(c.policy, revision=4, open_discoveries=tuple(additions)))
    record("E2_discovery_requires_scope_review", discovered=additions)
    new_routes = ROUTES + (RouteSpec("delivery", ("tenant",)),)
    p5 = CoveragePolicy(5, new_routes, c.policy.bindings +
                       (binding("delivery", "tenant", REPO_DELIVERY),))
    c.update_policy(p5, c.core.claims + (REPO_DELIVERY,))
    c.observe_routes(RouteView(c.view.epoch + 1, c.view.modes + (("delivery", False),)))
    all_three = ScopedOperation(("api", "batch", "delivery"))
    record("E2_route_declared_evidence_missing", all_three)
    c.revalidate(all_three)
    record("E2_delivery_counterexample", all_three)
    fixed = source.replace("def scheduled_delivery(actor, row):\n    deliver(row)",
        "def scheduled_delivery(actor, row):\n    if permitted(actor, row):\n        deliver(row)")
    assert fixed != source
    c.observe(c.core.snapshot.with_changes(**{"document_routes.py": fixed}))
    c.revalidate(all_three)
    record("E2_fixed_all_declared_routes", all_three)
    return {"rows": rows, "limited_activation": limited["status"],
            "full_activation": full["status"], "local_boundary_probe": enforcement,
            "name_candidates": list(named.candidates), "effect_candidates": list(structural.candidates),
            "inventory_complete_in_reality": False,
            "note": "ALLOW remains bounded by the trusted declared inventory; scanner findings require reviewed reclassification"}


if __name__ == "__main__":
    import json
    print(json.dumps(run_lifecycle(), ensure_ascii=False, indent=2))


def compare_coverage() -> list[dict]:
    """Same evidence, two admission policies; an author-declared decision table.

    The baseline checks every registered claim plus authority, but has neither
    route requirements nor runtime route scope. Not a baseline for CI at large.
    """
    from change_control import Operation, Authority
    rows = []
    def ready():
        c = initial_controller(); c.revalidate(API_ONLY); return c
    def batch(c, good=False):
        c.update_policy(replace(c.policy, revision=2, bindings=c.policy.bindings+
            (binding("batch", "tenant", BATCH_CLAIM),)), CLAIMS+(BATCH_CLAIM,))
        if good:
            c.observe(c.core.snapshot.with_changes(**{"batch.py": BATCH_GOOD}))
        c.revalidate(ALL_KNOWN)
    def add(name, c, op, expected):
        old = Controller(c.core.snapshot, c.core.claims, c.core.authority)
        old.records = c.core.records
        old_result = old.decide(Operation(action=op.action, environment=op.environment, tenants=op.tenants))
        new = c.decide(op)
        rows.append({"case": name, "expected_under_declared_scope_policy": expected,
            "registered_claims_only": old_result.verdict, "scoped_coverage": new.verdict,
            "reasons": list(new.reasons), "same_evidence_records": len(c.core.records)})
    add("missing_mapping_full", ready(), ALL_KNOWN, "HOLD")
    add("missing_mapping_disabled_batch_api_only", ready(), API_ONLY, "ALLOW")
    c=ready();c.observe_routes(RouteView(2,(("api",False),("batch",None))))
    add("disabled_state_unobserved",c,API_ONLY,"HOLD")
    c=ready();c.update_policy(replace(c.policy,revision=2,bindings=c.policy.bindings+
        (binding("batch","tenant",CLAIMS[0]),)))
    add("api_check_mislabeled_as_batch",c,ALL_KNOWN,"HOLD")
    c=ready();batch(c,True)
    add("all_requirements_pass",c,ALL_KNOWN,"ALLOW")
    c=ready();batch(c)
    add("batch_counterexample_full",c,ALL_KNOWN,"DENY")
    add("batch_counterexample_disabled_api_only",c,API_ONLY,"ALLOW")
    c=ready();c.core.set_authority(Authority(enabled=False,actions=("activate",),epoch=2))
    add("authority_revoked",c,API_ONLY,"DENY")
    c=ready();c.observe(c.core.snapshot.with_changes(**{"app.py":c.core.snapshot.read("app.py")+"\n# comment\n"}))
    add("relevant_evidence_stale",c,API_ONLY,"HOLD")
    c=ready()
    add("outside_environment_authority",c,replace(API_ONLY,environment="production"),"DENY")
    return rows
