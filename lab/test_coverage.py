from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import unittest

from change_control import Authority, Claim
from coverage_control import (CoveragePolicy, RouteSpec, RouteView, ScopedOperation)
from coverage_scenarios import (API_ONLY, ALL_KNOWN, APPROVED_SCOPES, ROUTES, binding,
                               initial_controller, initial_policy, run_lifecycle)
from scenarios import CLAIMS, BATCH_CLAIM, BATCH_GOOD


class CoverageTests(unittest.TestCase):
    def ready(self):
        c = initial_controller(); c.revalidate(API_ONLY)
        return c

    def add_batch(self, c):
        c.update_policy(replace(c.policy, revision=c.policy.revision+1,
            bindings=c.policy.bindings+(binding("batch", "tenant", BATCH_CLAIM),)),
            CLAIMS+(BATCH_CLAIM,))

    def test_known_gap_holds_even_when_all_existing_claims_pass(self):
        c = self.ready(); d=c.decide(ALL_KNOWN)
        self.assertEqual(d.verdict, "HOLD")
        self.assertIn("coverage_missing:batch:tenant", d.reasons)
        self.assertTrue(all(v.status == "CURRENT" for v in d.assessments))
        self.assertEqual((len(d.required),len(d.covered)),(5,4))

    def test_api_only_can_activate_with_observed_disabled_batch(self):
        self.assertEqual(self.ready().decide(API_ONLY).verdict, "ALLOW")

    def test_disabled_is_enforced_not_only_written_in_a_report(self):
        c=self.ready(); c.execute(c.decide(API_ONLY),"a")
        a={"role":"manager","tenant":"tenant-a"};r={"tenant":"tenant-a"}
        self.assertTrue(c.invoke_demo_route("api",a,r))
        self.assertFalse(c.invoke_demo_route("batch",a,r))

    def test_local_activation_is_limited_to_observed_tenant(self):
        c=self.ready();c.execute(c.decide(API_ONLY),"k")
        self.assertFalse(c.invoke_demo_route("api",{"role":"manager","tenant":"tenant-b"},{"tenant":"tenant-b"}))

    def test_partial_cohort_cannot_activate_entire_view(self):
        c=self.ready();c.observe_routes(RouteView(2,c.view.modes,tenants=("tenant-a","tenant-b")))
        self.assertEqual(c.decide(API_ONLY).verdict,"HOLD")

    def test_unknown_disabled_state_holds(self):
        c=self.ready();c.observe_routes(RouteView(2,(("api",False),("batch",None))))
        self.assertEqual(c.decide(API_ONLY).verdict,"HOLD")

    def test_missing_runtime_inventory_holds(self):
        c=self.ready();c.observe_routes(RouteView(2,(("api",False),)))
        self.assertEqual(c.decide(API_ONLY).verdict,"HOLD")

    def test_unobserved_runtime_holds(self):
        c=self.ready();c.observe_routes(RouteView(2,c.view.modes,observed=False))
        self.assertEqual(c.decide(API_ONLY).verdict,"HOLD")

    def test_other_tenant_observation_is_not_accepted(self):
        c=self.ready();c.core.set_authority(Authority(actions=("activate",),tenants=("tenant-a","tenant-b"),epoch=2))
        self.assertEqual(c.decide(replace(API_ONLY,tenants=("tenant-b",))).verdict,"HOLD")

    def test_other_environment_observation_is_not_accepted(self):
        c=self.ready();c.core.set_authority(Authority(actions=("activate",),environments=("staging","production"),epoch=2))
        self.assertEqual(c.decide(replace(API_ONLY,environment="production")).verdict,"HOLD")

    def test_already_active_batch_cannot_be_excluded_by_request(self):
        c=self.ready();c.observe_routes(RouteView(2,(("api",True),("batch",True))))
        self.assertEqual(c.decide(API_ONLY).verdict,"DENY")
        self.assertIn("implicit_disable_not_supported",c.decide(API_ONLY).reasons)

    def test_new_mapping_does_not_fabricate_pass(self):
        c=self.ready();self.add_batch(c)
        self.assertEqual(c.decide(ALL_KNOWN).verdict,"HOLD")
        self.assertEqual(next(v.status for v in c.decide(ALL_KNOWN).assessments if v.claim_id==BATCH_CLAIM.id),"UNKNOWN")

    def test_mapped_bad_batch_denies(self):
        c=self.ready();self.add_batch(c);c.revalidate(ALL_KNOWN)
        self.assertEqual(c.decide(ALL_KNOWN).verdict,"DENY")

    def test_irrelevant_disabled_failed_claim_does_not_block_api(self):
        c=self.ready();self.add_batch(c);c.revalidate(ALL_KNOWN)
        self.assertEqual(c.decide(API_ONLY).verdict,"ALLOW")

    def test_fix_requires_new_evidence(self):
        c=self.ready();self.add_batch(c);c.revalidate(ALL_KNOWN)
        c.observe(c.core.snapshot.with_changes(**{"batch.py":BATCH_GOOD}))
        self.assertEqual(c.decide(ALL_KNOWN).verdict,"HOLD")
        c.revalidate(ALL_KNOWN)
        self.assertEqual(c.decide(ALL_KNOWN).verdict,"ALLOW")

    def test_wrong_route_evaluator_cannot_fill_gap(self):
        c=self.ready();c.update_policy(replace(c.policy,revision=2,
            bindings=c.policy.bindings+(binding("batch","tenant",CLAIMS[0]),)))
        self.assertIn("evaluator_scope_mismatch:batch:tenant",c.decide(ALL_KNOWN).reasons)

    def test_claim_meaning_change_invalidates_mapping(self):
        c=self.ready();new=replace(CLAIMS[0],statement="different meaning")
        c.update_policy(replace(c.policy,revision=2),(new,)+CLAIMS[1:])
        self.assertIn("coverage_binding_stale:api:tenant",c.decide(API_ONLY).reasons)

    def test_missing_claim_holds(self):
        c=self.ready();c.update_policy(replace(c.policy,revision=2),CLAIMS[1:])
        self.assertIn("claim_missing:api:tenant",c.decide(API_ONLY).reasons)

    def test_discovered_unclassified_route_holds(self):
        c=self.ready();c.update_policy(replace(c.policy,revision=2,open_discoveries=("new-route",)))
        self.assertIn("discovery_unresolved:new-route",c.decide(API_ONLY).reasons)

    def test_unknown_requested_route_denies(self):
        self.assertEqual(self.ready().decide(ScopedOperation(("missing",))).verdict,"DENY")

    def test_runtime_extra_route_holds(self):
        c=self.ready();c.observe_routes(RouteView(2,c.view.modes+(("unknown",False),)))
        self.assertEqual(c.decide(API_ONLY).verdict,"HOLD")

    def test_empty_requested_scope_denied(self):
        self.assertEqual(self.ready().decide(ScopedOperation(())).verdict,"DENY")

    def test_duplicate_requested_scope_denied(self):
        self.assertEqual(self.ready().decide(ScopedOperation(("api","api"))).verdict,"DENY")

    def test_wrong_action_denied(self):
        self.assertEqual(self.ready().decide(replace(API_ONLY,action="delete")).verdict,"DENY")

    def test_revocation_at_execution(self):
        c=self.ready();d=c.decide(API_ONLY);c.core.set_authority(Authority(enabled=False,epoch=2))
        self.assertEqual(c.execute(d,"k")["status"],"deny")
        self.assertEqual(c.effect_count,0)

    def test_policy_change_stales_decision(self):
        c=self.ready();d=c.decide(API_ONLY);c.update_policy(replace(c.policy,revision=2))
        self.assertEqual(c.execute(d,"k")["status"],"hold")

    def test_runtime_change_stales_decision(self):
        c=self.ready();d=c.decide(API_ONLY);c.observe_routes(RouteView(2,c.view.modes))
        self.assertEqual(c.execute(d,"k")["status"],"hold")

    def test_snapshot_change_stales_decision(self):
        c=self.ready();d=c.decide(API_ONLY);c.observe(c.core.snapshot.with_changes(**{"docs/readme.md":"changed"}))
        self.assertEqual(c.execute(d,"k")["status"],"hold")

    def test_idempotent_same_intent(self):
        c=self.ready();d=c.decide(API_ONLY)
        self.assertEqual(c.execute(d,"k")["status"],"succeeded")
        self.assertEqual(c.execute(d,"k")["status"],"already_completed")
        self.assertEqual(c.effect_count,1)

    def test_id_collision_rejected(self):
        c=self.ready();d=c.decide(API_ONLY);c.execute(d,"k")
        with self.assertRaises(ValueError):c.execute(replace(d,operation=ALL_KNOWN),"k")

    def test_concurrent_execution_single_local_effect(self):
        c=self.ready();d=c.decide(API_ONLY)
        with ThreadPoolExecutor(max_workers=4) as pool:
            rows=list(pool.map(lambda _:c.execute(d,"k"),range(12)))
        self.assertEqual(sum(r["effect_executed"] for r in rows),1)

    def test_duplicate_requirements_rejected(self):
        with self.assertRaises(ValueError):CoveragePolicy(1,(RouteSpec("api",("tenant","tenant")),),())

    def test_empty_requirements_rejected(self):
        with self.assertRaises(ValueError):CoveragePolicy(1,(RouteSpec("api",()),),())

    def test_duplicate_mapping_rejected(self):
        p=initial_policy()
        with self.assertRaises(ValueError):replace(p,bindings=p.bindings+(p.bindings[0],))

    def test_epochs_must_increase(self):
        c=self.ready()
        with self.assertRaises(ValueError):c.observe_routes(c.view)
        with self.assertRaises(ValueError):c.update_policy(c.policy)

    def test_coverage_comparison_matches_declared_decision_table(self):
        from coverage_scenarios import compare_coverage
        rows=compare_coverage()
        self.assertEqual(len(rows),10)
        self.assertTrue(all(r["scoped_coverage"]==r["expected_under_declared_scope_policy"] for r in rows))
        by_id={r["case"]:r for r in rows}
        self.assertEqual(by_id["batch_counterexample_disabled_api_only"]["registered_claims_only"],"DENY")
        self.assertEqual(by_id["missing_mapping_full"]["registered_claims_only"],"ALLOW")

    def test_lifecycle(self):
        r=run_lifecycle();states={x["step"]:x["verdict"] for x in r["rows"]}
        self.assertEqual(states["E1_declared_batch_without_check"],"HOLD")
        self.assertEqual(states["E2_inventory_missing_scheduled_delivery"],"ALLOW")
        self.assertEqual(states["E2_discovery_requires_scope_review"],"HOLD")
        self.assertEqual(states["E2_delivery_counterexample"],"DENY")
        self.assertEqual(states["E2_fixed_all_declared_routes"],"ALLOW")
        self.assertEqual(r["local_boundary_probe"],{"api_allowed":True,"batch_allowed":False})


if __name__=="__main__":unittest.main()
