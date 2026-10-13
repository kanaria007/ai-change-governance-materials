"""Author-designed, synthetic fixtures. Not a reconstruction of a real repository."""
import json
from change_control import Claim, Snapshot, Controller, Authority

APP_V1 = '''def can_export(actor, row):
    return actor["role"] == "manager" and actor["tenant"] == row["tenant"]

def render(row):
    return row["title"]
'''
APP_BAD = APP_V1.replace(' and actor["tenant"] == row["tenant"]', '')
APP_V2 = APP_V1.replace('return row["title"]', 'return row["display_title"]')
WIRE_GOOD = '''def encode(allowed):
    return {"can_export": allowed}
'''
WIRE_BAD = '''def encode(allowed):
    return {"can_export": allowed} if allowed else {}
'''
CLIENT = '''def visible(payload):
    return payload.get("can_export", True)
'''
BATCH_GOOD = '''def can_export_batch(actor, row):
    return actor["role"] == "manager" and actor["tenant"] == row["tenant"]
'''
BATCH_BAD = BATCH_GOOD.replace(' and actor["tenant"] == row["tenant"]', '')
TENANT_CASES = [
    {"name": "same-tenant-manager", "actor": {"role": "manager", "tenant": "tenant-a"},
     "row": {"tenant": "tenant-a"}, "expected": True},
    {"name": "cross-tenant-manager", "actor": {"role": "manager", "tenant": "tenant-a"},
     "row": {"tenant": "tenant-b"}, "expected": False},
    {"name": "same-tenant-viewer", "actor": {"role": "viewer", "tenant": "tenant-a"},
     "row": {"tenant": "tenant-a"}, "expected": False},
]
CLAIMS = (
    Claim("tenant-isolation", "declared API actor/tenant cases hold",
          ("app.py", "tenant_cases.json"), "tenant-v1"),
    Claim("false-preservation", "explicit false survives the declared wire route",
          ("wire.py", "client.py"), "wire-v1"),
    Claim("storage-readable", "the declared stored row can be rendered",
          ("app.py", "data.json"), "storage-v1"),
)
BATCH_CLAIM = Claim("batch-isolation", "declared batch actor/tenant cases hold",
                    ("batch.py", "tenant_cases.json"), "batch-v1")


def base() -> Snapshot:
    return Snapshot.of({"app.py": APP_V1, "wire.py": WIRE_GOOD, "client.py": CLIENT,
        "batch.py": BATCH_GOOD, "data.json": json.dumps({"row": {"title": "sample"}}),
        "tenant_cases.json": json.dumps(TENANT_CASES),
        "environment.json": '{"name":"local-lab","profile":1}',
        "docs/readme.md": "first documentation version"})


def smoke(snapshot: Snapshot) -> bool:
    # Deliberately limited positive-only CI. Not representative of all real CI.
    from change_control import _module
    actor = {"tenant": "tenant-a", "role": "manager"}
    row = {"tenant": "tenant-a"}
    return (_module(snapshot, "app.py")["can_export"](actor, row) is True
            and _module(snapshot, "client.py")["visible"](
                _module(snapshot, "wire.py")["encode"](True)) is True)


def scenario_results() -> dict:
    results = {}
    for label, resource, body in [("A_guard_removed", "app.py", APP_BAD),
                                  ("B_false_lost", "wire.py", WIRE_BAD)]:
        control = Controller(base(), CLAIMS)
        control.revalidate()
        changed = base().with_changes(**{resource: body})
        control.observe(changed)
        before = control.decide()
        control.revalidate()
        after = control.decide()
        results[label] = {"smoke_pass": smoke(changed), "before_revalidation": before.verdict,
            "after_revalidation": after.verdict,
            "claim_states": {x.claim_id: x.status for x in after.assessments}}

    control = Controller(base(), CLAIMS); control.revalidate()
    # A harmless implementation edit still changes two declared proof contexts.
    control.observe(base().with_changes(**{"app.py": APP_V1 + "\n# explanatory comment\n"}))
    before = control.decide(); control.revalidate(); after = control.decide()
    results["C_safe_change_old_evidence"] = {"before_revalidation": before.verdict,
                                            "after_revalidation": after.verdict}

    control = Controller(base(), CLAIMS); control.revalidate()
    prior = control.decide()
    control.set_authority(Authority(enabled=False, epoch=2))
    results["D_revoked_after_admission"] = control.execute(prior, "op-d")

    incomplete = Controller(base().with_changes(**{"batch.py": BATCH_BAD}), CLAIMS)
    incomplete.revalidate()
    extended = Controller(incomplete.snapshot, CLAIMS + (BATCH_CLAIM,))
    extended.revalidate()
    results["E_undeclared_batch_route"] = {"old_policy": incomplete.decide().verdict,
        "explicitly_extended_policy": extended.decide().verdict,
        "automatic_discovery": False}

    control = Controller(base(), CLAIMS); control.revalidate()
    changed_data = json.dumps({"row": {"display_title": "sample"}})
    control.observe(base().with_changes(**{"app.py": APP_V2, "data.json": changed_data}))
    control.revalidate()
    intermediate = control.decide()
    control.observe(base().with_changes(**{"data.json": changed_data}))
    before = control.decide(); control.revalidate(); after = control.decide()
    results["F_code_only_rollback"] = {"migrated": intermediate.verdict,
        "after_code_revert_before_revalidation": before.verdict,
        "after_revalidation": after.verdict}
    return results


def compare_revalidation() -> dict:
    """Same declared claims and current-authority check, differing reuse rules.

    Both strategies evaluate all newly seen contexts eventually. No AI review
    is performed. This is a constructed trace, not an independent benchmark.
    """
    s0 = base()
    s1 = s0.with_changes(**{"docs/readme.md": "second documentation version"})
    s2 = s1.with_changes(**{"wire.py": WIRE_GOOD + "\n# harmless wire comment\n"})
    s3 = s2.with_changes(**{"wire.py": WIRE_BAD})
    s4 = s2  # A known fixed wire context; old FAIL does not bind this context.
    s5 = s4.with_changes(**{"app.py": APP_V1 + "\n# harmless app comment\n"})
    labels = ["initial", "docs_only", "wire_comment", "wire_fault", "wire_restored", "app_comment"]
    modes = {}
    for mode in ("full_recheck", "dependency_reuse"):
        control = Controller(s0, CLAIMS)
        rows = []
        for label, snapshot in zip(labels, (s0, s1, s2, s3, s4, s5)):
            control.observe(snapshot)
            before_count = control.check_runs
            before = control.decide().verdict
            control.revalidate(force=mode == "full_recheck")
            after = control.decide().verdict
            rows.append({"step": label, "before": before, "after": after,
                         "checker_invocations": control.check_runs - before_count})
        modes[mode] = {"rows": rows, "checker_invocations": control.check_runs}
    return modes
