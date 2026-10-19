"""Manifest verification must fail closed on unexpected or modified source."""
import hashlib,json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import verify_package

class PackageTests(unittest.TestCase):
    def fixture(self,root):
        (root/'app'/'src').mkdir(parents=True)
        (root/'app'/'tests').mkdir(parents=True)
        (root/'tests').mkdir(parents=True)
        (root/'app'/'src'/'agent.py').write_text('safe',encoding='utf8')
        digest=hashlib.sha256(b'safe').hexdigest()
        (root/'manifest.json').write_text(json.dumps({'files':{'app/src/agent.py':digest}}),encoding='utf8')
        return root
    def test_good_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture(pathlib.Path(t))
            with patch.object(verify_package,'ROOT',root),patch.object(verify_package,'MANIFEST',root/'manifest.json'):
                self.assertEqual(verify_package.verify(),1)
    def test_tampered_source_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture(pathlib.Path(t))
            (root/'app'/'src'/'agent.py').write_text('bad',encoding='utf8')
            with patch.object(verify_package,'ROOT',root),patch.object(verify_package,'MANIFEST',root/'manifest.json'):
                with self.assertRaisesRegex(ValueError,'FILE_HASH_MISMATCH'):verify_package.verify()
    def test_unexpected_python_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture(pathlib.Path(t))
            (root/'app'/'src'/'malicious.py').write_text('pass',encoding='utf8')
            with patch.object(verify_package,'ROOT',root),patch.object(verify_package,'MANIFEST',root/'manifest.json'):
                with self.assertRaisesRegex(ValueError,'UNEXPECTED_PYTHON_FILE'):verify_package.verify()
    def test_traversal_entry_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture(pathlib.Path(t))
            (root/'manifest.json').write_text(json.dumps({'files':{'../evil.py':'a'*64}}),encoding='utf8')
            with patch.object(verify_package,'ROOT',root),patch.object(verify_package,'MANIFEST',root/'manifest.json'):
                with self.assertRaisesRegex(ValueError,'MANIFEST_PATH_INVALID'):verify_package.verify()
    def test_missing_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=self.fixture(pathlib.Path(t))
            (root/'manifest.json').unlink()
            with patch.object(verify_package,'ROOT',root),patch.object(verify_package,'MANIFEST',root/'manifest.json'):
                with self.assertRaisesRegex(ValueError,'MANIFEST_MISSING'):verify_package.verify()
if __name__=='__main__':unittest.main()
