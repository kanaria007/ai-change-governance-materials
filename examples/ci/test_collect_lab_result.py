import unittest
from collect_lab_result import classify, digest


class CollectionTests(unittest.TestCase):
    def test_completed_success(self):
        self.assertEqual(classify(0, "Ran 107 tests in 1.0s\n\nOK\n", True),
                         ("PASS", 107, "declared_lab_tests_passed"))
    def test_completed_failure(self):
        self.assertEqual(classify(1, "Ran 107 tests in 1.0s\nFAILED\n", True)[0], "FAIL")
    def test_zero_tests_is_not_success(self):
        self.assertEqual(classify(0, "Ran 0 tests in 0.0s\nOK\n", True)[0], "ERROR")
    def test_missing_summary_is_not_success(self):
        self.assertEqual(classify(0, "finished", True)[0], "ERROR")
    def test_changed_inputs_invalidate_success(self):
        self.assertEqual(classify(0, "Ran 1 test in 0.1s\nOK\n", False)[0], "ERROR")
    def test_interruption_is_not_success(self):
        self.assertEqual(classify(-9, "interrupted", True)[0], "ERROR")
    def test_success_without_ok_is_not_accepted(self):
        self.assertEqual(classify(0, "Ran 2 tests in 0.1s\n", True)[0], "ERROR")
    def test_digest_is_bound_to_log_bytes(self):
        self.assertNotEqual(digest(b"OK\n"), digest(b"FAIL\n"))


if __name__ == "__main__":
    unittest.main()
