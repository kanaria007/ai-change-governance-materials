from pathlib import Path
import unittest
from route_discovery import scan, compare, probe
from run_expansion import evaluate_set, select_strategy

HERE=Path(__file__).resolve().parent


class DiscoveryTests(unittest.TestCase):
    def fixture(self,name):return (HERE/"discovery_fixtures"/name).read_text()

    def test_name_misses_generic_wrapper(self):
        r=scan(self.fixture("development/d1.py"),"name")
        self.assertNotIn("nightly",r.candidates)

    def test_reverse_call_graph_finds_generic_wrapper(self):
        r=scan(self.fixture("development/d1.py"),"effect")
        self.assertIn("nightly",r.candidates)

    def test_stronger_name_baseline_finds_named_helper(self):
        r=scan(self.fixture("development/d2.py"),"name_callers")
        self.assertIn("run_job",r.candidates)

    def test_deterministic_cycle_terminates(self):
        s="@entrypoint\ndef start(a,b):\n    first()\ndef first():\n    second()\ndef second():\n    first()\n    emit_document({})\n"
        self.assertIn("start",scan(s,"effect").candidates)

    def test_parse_error_is_not_empty_success(self):
        r=scan("def broken(","effect")
        self.assertIsNotNone(r.parse_error)
        self.assertTrue(r.unresolved)

    def test_unknown_method_fails(self):
        with self.assertRaises(ValueError):scan("", "unknown")

    def test_dynamic_callback_is_reported_not_discovered(self):
        r=scan(self.fixture("limits/c1.py"),"effect")
        self.assertNotIn("scheduled_hook",r.candidates)
        self.assertIn("scheduled_hook",r.unresolved)

    def test_unregistered_sink_is_unresolved(self):
        r=scan(self.fixture("limits/c2.py"),"effect")
        self.assertNotIn("legacy_writer",r.candidates)
        self.assertIn("legacy_writer",r.unresolved)

    def test_alias_limit_is_retained(self):
        r=scan(self.fixture("limits/c3.py"),"effect")
        self.assertNotIn("indirect_job",r.candidates)
        self.assertIn("indirect_job",r.unresolved)

    def test_unreachable_branch_is_false_positive(self):
        r=compare(self.fixture("limits/c3.py"),"effect")
        self.assertIn("unreachable",r["unnecessary"])

    def test_public_sample_is_not_private_document(self):
        s=self.fixture("application/t3.py")
        self.assertNotIn("public_sample",probe(s)["positive"])
        self.assertIn("public_sample",scan(s,"effect").candidates)

    def test_selection_uses_only_development_totals(self):
        dev=evaluate_set(HERE,"development")
        self.assertEqual(select_strategy(dev),"effect")

    def test_different_fixtures_follow_frozen_strategy(self):
        method=select_strategy(evaluate_set(HERE,"development"))
        app=evaluate_set(HERE,"application")["totals"][method]
        self.assertEqual((app["tp"],app["fp"],app["fn"]),(6,1,0))

    def test_limits_do_not_disappear_from_metrics(self):
        result=evaluate_set(HERE,"limits")["totals"]
        self.assertEqual(result["effect"]["fn"],3)
        self.assertEqual(result["effect"]["unresolved_count"],3)
        self.assertEqual(result["all_entries"]["fn"],0)

    def test_every_comparator_uses_same_population(self):
        r=evaluate_set(HERE,"application")["totals"]
        self.assertTrue(all(sum(v[k] for k in ("tp","fp","fn","tn"))==12 for v in r.values()))
        self.assertEqual(len({v["source_bytes"] for v in r.values()}),1)

    def test_undecorated_function_outside_declared_entrypoint_surface(self):
        s="def handler(actor,row):\n    emit_document(row)\n"
        self.assertEqual(scan(s,"effect").entries,())
        # Explicitly a known limitation, not evidence that no real route exists.


if __name__=="__main__":unittest.main()
