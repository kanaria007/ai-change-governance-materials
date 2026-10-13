"""Regression tests for candidate, approved runtime and observed runtime separation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest

from change_control import Authority
from coverage_control import RuntimeObservation, RouteView
from coverage_scenarios import initial_controller, API_ONLY, ALL_KNOWN
from scenarios import APP_BAD, APP_V1

SAME = {"role": "manager", "tenant": "tenant-a"}
CROSS = {"tenant": "tenant-b"}
ROW = {"tenant": "tenant-a"}
# The additional attribute is deliberately outside the original three fixtures.
# It makes it observable which of two fixture-compatible versions is running.
RESTRICTED = APP_V1.replace('return actor["role"]',
                           'return not actor.get("suspended", False) and actor["role"]')


class RuntimeBoundaryTests(unittest.TestCase):
    def active(self):
        c = initial_controller()
        c.revalidate(API_ONLY)
        self.assertEqual(c.execute(c.decide(API_ONLY), "first")["status"], "succeeded")
        return c

    def test_review_counterexample_unverified_candidate_never_becomes_live(self):
        c = self.active()
        self.assertFalse(c.invoke_demo_route("api", SAME, CROSS))
        c.observe(c.core.snapshot.with_changes(**{"app.py": APP_BAD}))
        self.assertEqual(c.decide(API_ONLY).verdict, "HOLD")
        self.assertFalse(c.invoke_demo_route("api", SAME, CROSS))

    def test_no_approved_artifact_means_no_runtime_execution(self):
        c = initial_controller()
        c.observe_routes(RouteView(2, (("api", True), ("batch", False))))
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))
        self.assertIsNone(c.active_snapshot)

    def test_observe_candidate_preserves_active_identity_and_generation(self):
        c = self.active()
        old, generation = c.active_snapshot, c.release_generation
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": APP_BAD}))
        self.assertEqual(c.active_snapshot, old)
        self.assertEqual(c.release_generation, generation)
        self.assertNotEqual(c.candidate_snapshot.fingerprint, old.fingerprint)

    def test_confirmed_bad_candidate_also_cannot_replace_runtime(self):
        c = self.active()
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": APP_BAD}))
        c.revalidate(API_ONLY)
        self.assertEqual(c.decide(API_ONLY).verdict, "DENY")
        self.assertFalse(c.invoke_demo_route("api", SAME, CROSS))
        self.assertTrue(c.invoke_demo_route("api", SAME, ROW))

    def test_revalidation_alone_does_not_publish_candidate(self):
        c = self.active()
        suspended = SAME | {"suspended": True}
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": RESTRICTED}))
        c.revalidate(API_ONLY)
        self.assertEqual(c.decide(API_ONLY).verdict, "ALLOW")
        self.assertTrue(c.invoke_demo_route("api", suspended, ROW))

    def test_successful_execute_publishes_exact_new_artifact(self):
        c = self.active()
        old_ref = c.active_snapshot.fingerprint
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": RESTRICTED}))
        c.revalidate(API_ONLY)
        d = c.decide(API_ONLY)
        result = c.execute(d, "new-version")
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(c.active_snapshot.fingerprint, d.snapshot_ref)
        self.assertEqual(result["previous_active_ref"], old_ref)
        self.assertEqual(c.release_generation, 2)
        self.assertFalse(c.invoke_demo_route("api", SAME | {"suspended": True}, ROW))
        self.assertTrue(c.invoke_demo_route("api", SAME, ROW))

    def test_stale_allow_does_not_publish_changed_candidate(self):
        c = self.active()
        old_ref = c.active_snapshot.fingerprint
        d = c.decide(API_ONLY)
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"docs/readme.md": "next"}))
        self.assertEqual(c.decide(API_ONLY).verdict, "ALLOW")
        self.assertEqual(c.execute(d, "stale")["status"], "hold")
        self.assertEqual(c.active_snapshot.fingerprint, old_ref)

    def test_denied_activation_does_not_change_active(self):
        c = self.active()
        old = c.active_snapshot
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": APP_BAD}))
        c.revalidate(API_ONLY)
        self.assertEqual(c.execute(c.decide(API_ONLY), "bad")["status"], "not_admitted")
        self.assertEqual(c.active_snapshot, old)
        self.assertEqual(c.effect_count, 1)

    def test_revoked_deployer_cannot_publish_new_code(self):
        c = self.active()
        d = c.decide(API_ONLY)
        old = c.active_snapshot
        c.core.set_authority(Authority(enabled=False, actions=("activate",), epoch=2))
        self.assertEqual(c.execute(d, "revoked")["status"], "deny")
        self.assertEqual(c.active_snapshot, old)
        # Revoking the deployer is not revoking a user's application permission.
        self.assertTrue(c.invoke_demo_route("api", SAME, ROW))

    def test_observing_candidate_as_runtime_neither_admits_nor_runs_it(self):
        c = self.active()
        bad = c.candidate_snapshot.with_changes(**{"app.py": APP_BAD})
        c.observe_candidate(bad)
        c.observe_runtime(replace(c.runtime_observation, epoch=3, snapshot_ref=bad.fingerprint))
        self.assertNotEqual(c.active_snapshot.fingerprint, bad.fingerprint)
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))
        self.assertFalse(c.invoke_demo_route("api", SAME, CROSS))
        self.assertIn("runtime_artifact_mismatch", c.decide(API_ONLY).reasons)

    def test_missing_runtime_observation_contains_existing_route(self):
        c = self.active()
        c.observe_runtime(replace(c.runtime_observation, epoch=3, observed=False))
        self.assertEqual(c.decide(API_ONLY).verdict, "HOLD")
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))

    def test_runtime_generation_mismatch_is_not_ignored(self):
        c = self.active()
        c.observe_runtime(replace(c.runtime_observation, epoch=3, release_generation=99))
        self.assertIn("runtime_artifact_mismatch", c.decide(API_ONLY).reasons)
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))

    def test_runtime_observation_of_other_tenant_cannot_clear_containment(self):
        c = self.active()
        c.observe_runtime(replace(c.runtime_observation, epoch=3, tenants=("tenant-b",)))
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))
        self.assertIn("runtime_observation_scope_mismatch", c.decide(API_ONLY).reasons)

    def test_runtime_observation_of_other_environment_cannot_clear_containment(self):
        c = self.active()
        c.observe_runtime(replace(c.runtime_observation, epoch=3, environment="production"))
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))

    def test_fresh_matching_observation_restores_only_approved_local_runtime(self):
        c = self.active()
        original = c.runtime_observation
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": APP_BAD}))
        c.observe_runtime(replace(original, epoch=3, observed=False))
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))
        c.observe_runtime(replace(original, epoch=4))
        self.assertTrue(c.invoke_demo_route("api", SAME, ROW))
        self.assertFalse(c.invoke_demo_route("api", SAME, CROSS))
        self.assertEqual(c.decide(API_ONLY).verdict, "HOLD")
        self.assertFalse(c.runtime_history[-2]["observed"])

    def test_old_runtime_observation_cannot_overwrite_new_one(self):
        c = self.active()
        with self.assertRaises(ValueError):
            c.observe_runtime(c.runtime_observation)

    def test_runtime_fact_does_not_activate_unapproved_route(self):
        c = self.active()
        c.observe_routes(replace(c.view, epoch=c.view.epoch + 1,
                                modes=(("api", True), ("batch", True))))
        self.assertFalse(c.invoke_demo_route("batch", SAME, ROW))
        self.assertFalse(c.invoke_demo_route("api", SAME, ROW))
        self.assertIn("runtime_route_mismatch", c.decide(ALL_KNOWN).reasons)

    def test_policy_update_does_not_publish_code(self):
        c = self.active()
        old = c.active_snapshot
        d = c.decide(API_ONLY)
        c.update_policy(replace(c.policy, revision=c.policy.revision + 1))
        self.assertEqual(c.execute(d, "policy-change")["status"], "hold")
        self.assertEqual(c.active_snapshot, old)

    def test_replay_old_operation_does_not_roll_back_new_active_release(self):
        c = initial_controller(); c.revalidate(API_ONLY)
        old_decision = c.decide(API_ONLY)
        c.execute(old_decision, "old")
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": RESTRICTED}))
        c.revalidate(API_ONLY)
        c.execute(c.decide(API_ONLY), "new")
        current_ref = c.active_snapshot.fingerprint
        self.assertEqual(c.execute(old_decision, "old")["status"], "already_completed")
        self.assertEqual(c.active_snapshot.fingerprint, current_ref)
        self.assertEqual(c.effect_count, 2)

    def test_candidate_updates_and_runtime_calls_share_no_code_pointer(self):
        c = self.active()
        initial = c.active_snapshot
        def update_and_call(index):
            source = APP_BAD if index % 2 else APP_V1
            c.observe_candidate(initial.with_changes(**{"app.py": source}))
            return c.invoke_demo_route("api", SAME, CROSS)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(update_and_call, range(40)))
        self.assertFalse(any(results))
        self.assertEqual(c.active_snapshot, initial)
        self.assertEqual(c.effect_count, 1)

    def test_runtime_observation_change_invalidates_pending_decision(self):
        c = self.active()
        d = c.decide(API_ONLY)
        c.observe_runtime(replace(c.runtime_observation, epoch=3))
        self.assertEqual(c.execute(d, "fresh-observation")["status"], "hold")

    def test_candidate_has_no_effect_on_disabled_route(self):
        c = self.active()
        c.observe_candidate(c.candidate_snapshot.with_changes(**{"app.py": RESTRICTED}))
        c.revalidate(API_ONLY)
        c.execute(c.decide(API_ONLY), "api-new")
        self.assertFalse(c.invoke_demo_route("batch", SAME, ROW))

    def test_invalid_runtime_generation_is_rejected(self):
        with self.assertRaises(ValueError):
            RuntimeObservation(0, None, 0)
        with self.assertRaises(ValueError):
            RuntimeObservation(1, None, -1)


if __name__ == "__main__":
    unittest.main()
