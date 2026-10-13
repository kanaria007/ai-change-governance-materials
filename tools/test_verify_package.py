"""Package consistency tests, separate from the teaching-model test count."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('verify_package', Path(__file__).resolve().parents[1] / 'verify_package.py')
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / 'lab').mkdir()
        (self.root / 'lab/sample.py').write_bytes(b'sample')
        self.manifest = {'schema':MOD.SCHEMA, 'tracked_globs':list(MOD.TRACKED_GLOBS), 'files':[{'path':'lab/sample.py','sha256':hashlib.sha256(b'sample').hexdigest(),'size_bytes':6}]}
        self.save()

    def save(self):
        self.raw = (json.dumps(self.manifest)+'\n').encode()
        (self.root / 'FILE-MANIFEST.json').write_bytes(self.raw)
        self.ref = hashlib.sha256(self.raw).hexdigest()

    def test_matching_book_binding(self):
        self.assertEqual(MOD.verify(self.root, self.ref), (1, []))

    def test_prefixed_digest(self):
        self.assertEqual(MOD.verify(self.root, 'sha256:'+self.ref), (1, []))

    def test_wrong_book_binding_fails_before_files(self):
        count, errors = MOD.verify(self.root, '0'*64)
        self.assertEqual(count, 0)
        self.assertTrue(errors)

    def test_invalid_binding(self):
        self.assertTrue(MOD.verify(self.root, 'n/a')[1])

    def test_file_mutation(self):
        (self.root / 'lab/sample.py').write_bytes(b'changed')
        self.assertTrue(MOD.verify(self.root, self.ref)[1])

    def test_missing_file(self):
        (self.root / 'lab/sample.py').unlink()
        self.assertTrue(MOD.verify(self.root, self.ref)[1])

    def test_unlisted_document_is_not_covered(self):
        (self.root / 'lab/README.md').write_bytes(b'x')
        self.assertEqual(MOD.verify(self.root, self.ref), (1, []))

    def test_new_experiment_source_cannot_be_silently_excluded(self):
        (self.root / 'lab/new_checker.py').write_text('pass\n')
        count, problems = MOD.verify(self.root, self.ref)
        self.assertEqual(count, 1)
        self.assertTrue(any('Unlisted experiment files' in p for p in problems))

    def test_new_experiment_result_cannot_be_silently_excluded(self):
        (self.root / 'lab/new_results.json').write_text('{}\n')
        self.assertTrue(any('Unlisted experiment files' in p for p in MOD.verify(self.root, self.ref)[1]))

    def test_document_typo_does_not_change_binding(self):
        (self.root / 'README.md').write_text('First draft\n')
        self.assertEqual(MOD.verify(self.root, self.ref), (1, []))
        (self.root / 'README.md').write_text('Corrected wording\n')
        self.assertEqual(MOD.verify(self.root, self.ref), (1, []))

    def test_path_escape(self):
        self.manifest['files'][0]['path'] = '../sample.py'
        self.save()
        self.assertTrue(MOD.verify(self.root, self.ref)[1])

    def test_duplicate_path(self):
        self.manifest['files'].append(dict(self.manifest['files'][0]))
        self.save()
        self.assertTrue(MOD.verify(self.root, self.ref)[1])

    def test_symlink(self):
        (self.root / 'lab/sample.py').unlink()
        (self.root / 'lab/sample.py').symlink_to(self.root/'lab/target.txt')
        (self.root / 'lab/target.txt').write_bytes(b'sample')
        self.assertTrue(MOD.verify(self.root, self.ref)[1])

if __name__ == '__main__':
    unittest.main()
