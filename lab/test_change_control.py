from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import unittest
from change_control import (Authority, Controller, Operation, Snapshot,
                            assess, digest_object, stable_json)
from scenarios import (APP_BAD, APP_V1, CLAIMS, WIRE_BAD, base,
                       compare_revalidation, scenario_results)


class ChangeControlTests(unittest.TestCase):
    def controller(self):
        c = Controller(base(), CLAIMS)
        c.revalidate()
        return c

    def test_canonical_key_order(self):
        self.assertEqual(digest_object({"b": 1, "a": True}),
                         digest_object({"a": True, "b": 1}))

    def test_float_rejected(self):
        with self.assertRaises(TypeError): stable_json({"score": 0.9})

    def test_nonstring_key_rejected(self):
        with self.assertRaises(TypeError): stable_json({1: "x"})

    def test_unobserved_input(self):
        c = Controller(base().with_changes(**{"app.py": None}), CLAIMS)
        c.revalidate()
        self.assertEqual(c.decide().verdict, "HOLD")
        self.assertEqual(c.decide().assessments[0].status, "UNKNOWN")

    def test_no_evidence_is_unknown(self):
        c = Controller(base(), CLAIMS)
        self.assertEqual(c.decide().assessments[0].status, "UNKNOWN")
        self.assertEqual(c.decide().verdict, "HOLD")

    def test_empty_claim_set_is_not_admissible(self):
        self.assertEqual(Controller(base(), ()).decide().verdict, "HOLD")

    def test_baseline_current(self):
        c = self.controller()
        self.assertEqual(c.decide().verdict, "ALLOW")
        self.assertEqual(c.check_runs, 3)

    def test_changed_code_stales_evidence(self):
        c = self.controller()
        c.observe(base().with_changes(**{"app.py": APP_BAD}))
        states = {a.claim_id: a.status for a in c.decide().assessments}
        self.assertEqual(states["tenant-isolation"], "STALE")
        self.assertEqual(states["false-preservation"], "CURRENT")
        self.assertEqual(c.decide().verdict, "HOLD")

    def test_stale_does_not_mean_broken(self):
        c = self.controller()
        c.observe(base().with_changes(**{"app.py": APP_V1 + "\n# harmless\n"}))
        self.assertEqual(c.decide().verdict, "HOLD")
        c.revalidate()
        self.assertEqual(c.decide().verdict, "ALLOW")

    def test_unrelated_document_change_reuses_claim_evidence(self):
        c = self.controller()
        c.observe(base().with_changes(**{"docs/readme.md": "edited"}))
        self.assertEqual(c.decide().verdict, "ALLOW")
        self.assertEqual(len(c.revalidate()), 0)

    def test_known_counterexample_denies(self):
        c = self.controller()
        c.observe(base().with_changes(**{"app.py": APP_BAD})); c.revalidate()
        self.assertEqual(c.decide().verdict, "DENY")
        self.assertEqual(c.decide().assessments[0].status, "CONTRADICTED")

    def test_passing_retry_does_not_erase_failure(self):
        c = self.controller()
        c.observe(base().with_changes(**{"app.py": APP_BAD})); c.revalidate()
        failure = [r for r in c.records if r.claim_id == "tenant-isolation" and r.outcome == "FAIL"][0]
        # Deliberate white-box conflict injection, not an externally accepted receipt.
        c.records += (replace(failure, sequence=len(c.records) + 1, outcome="PASS"),)
        self.assertEqual(c.decide().verdict, "DENY")

    def test_evaluator_runtime_error_is_unknown_not_counterexample(self):
        c = self.controller()
        c.observe(base().with_changes(**{"wire.py": "def encode(value):\n    raise RuntimeError('runner')\n"}))
        c.revalidate()
        state = [a for a in c.decide().assessments if a.claim_id == "false-preservation"][0]
        self.assertEqual(state.status, "UNKNOWN")
        self.assertEqual(c.decide().verdict, "HOLD")

    def test_claim_meaning_change_stales_same_code(self):
        c = self.controller()
        revised = replace(CLAIMS[0], statement="a revised declaration of the protected contract")
        self.assertEqual(assess(c.snapshot, revised, c.records).status, "STALE")

    def test_environment_change_stales_all_claims(self):
        c = self.controller()
        c.observe(base().with_changes(**{"environment.json": '{"name":"other"}'}))
        self.assertTrue(all(x.status == "STALE" for x in c.decide().assessments))

    def test_revocation_blocks_previously_admitted_operation(self):
        c = self.controller(); decision = c.decide()
        c.set_authority(Authority(enabled=False, epoch=2))
        self.assertEqual(c.execute(decision, "k")["status"], "deny")
        self.assertEqual(c.effect_count, 0)

    def test_unobserved_authority_holds(self):
        c = self.controller(); c.set_authority(Authority(observed=False, epoch=2))
        self.assertEqual(c.decide().verdict, "HOLD")

    def test_wrong_environment_denied(self):
        self.assertEqual(self.controller().decide(Operation(environment="production")).verdict, "DENY")

    def test_wrong_tenant_denied(self):
        self.assertEqual(self.controller().decide(Operation(tenants=("tenant-b",))).verdict, "DENY")

    def test_empty_tenant_scope_denied(self):
        self.assertEqual(self.controller().decide(Operation(tenants=())).verdict, "DENY")

    def test_authority_epoch_must_increase(self):
        with self.assertRaises(ValueError): self.controller().set_authority(Authority(epoch=1))

    def test_old_decision_requires_reissue_even_if_evidence_survives(self):
        c = self.controller(); decision = c.decide()
        c.observe(base().with_changes(**{"docs/readme.md": "edited"}))
        self.assertEqual(c.decide().verdict, "ALLOW")
        self.assertEqual(c.execute(decision, "k")["status"], "hold")
        self.assertEqual(c.effect_count, 0)

    def test_nonadmitted_cannot_execute(self):
        c = Controller(base(), CLAIMS)
        self.assertEqual(c.execute(c.decide(), "k")["status"], "not_admitted")
        self.assertEqual(c.effect_count, 0)

    def test_execution_is_idempotent_for_the_same_intent(self):
        c = self.controller(); decision = c.decide()
        self.assertEqual(c.execute(decision, "k")["status"], "succeeded")
        self.assertEqual(c.execute(decision, "k")["status"], "already_completed")
        self.assertEqual(c.effect_count, 1)

    def test_idempotency_key_collision_denied(self):
        c = self.controller(); c.execute(c.decide(), "k")
        c.observe(base().with_changes(**{"docs/readme.md": "edited"}))
        with self.assertRaises(ValueError): c.execute(c.decide(), "k")
        self.assertEqual(c.effect_count, 1)

    def test_ack_loss_never_blindly_retries(self):
        c = self.controller(); decision = c.decide()
        self.assertEqual(c.execute(decision, "k", lose_ack=True)["status"], "unknown")
        self.assertEqual(c.execute(decision, "k")["status"], "unknown")
        self.assertEqual(c.effect_count, 1)

    def test_empty_idempotency_key_denied(self):
        c = self.controller()
        with self.assertRaises(ValueError): c.execute(c.decide(), "")

    def test_concurrent_calls_produce_one_local_effect(self):
        c = self.controller(); decision = c.decide()
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda _: c.execute(decision, "same-key"), range(24)))
        self.assertEqual(sum(r["effect_executed"] for r in rows), 1)
        self.assertEqual(c.effect_count, 1)

    def test_record_history_survives_revalidation(self):
        c = self.controller(); before = c.records
        c.observe(base().with_changes(**{"wire.py": WIRE_BAD})); c.revalidate()
        self.assertEqual(c.records[:len(before)], before)
        self.assertGreater(len(c.records), len(before))

    def test_six_designed_scenarios(self):
        r = scenario_results()
        self.assertEqual(r["A_guard_removed"]["after_revalidation"], "DENY")
        self.assertEqual(r["B_false_lost"]["after_revalidation"], "DENY")
        self.assertEqual(r["C_safe_change_old_evidence"]["after_revalidation"], "ALLOW")
        self.assertEqual(r["D_revoked_after_admission"]["status"], "deny")
        self.assertEqual(r["E_undeclared_batch_route"]["old_policy"], "ALLOW")
        self.assertEqual(r["E_undeclared_batch_route"]["explicitly_extended_policy"], "DENY")
        self.assertEqual(r["F_code_only_rollback"]["after_revalidation"], "DENY")

    def test_reuse_and_full_recheck_agree_on_this_trace(self):
        r = compare_revalidation()
        expected = ["ALLOW", "ALLOW", "ALLOW", "DENY", "ALLOW", "ALLOW"]
        for mode in r.values():
            self.assertEqual([x["after"] for x in mode["rows"]], expected)
        self.assertEqual(r["full_recheck"]["checker_invocations"], 18)
        self.assertEqual(r["dependency_reuse"]["checker_invocations"], 7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
