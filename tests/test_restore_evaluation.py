"""Offline publication packaging checks; no scoring or network requests."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from tools.restore_evaluation_artifacts import restore,digest


class RestoreEvaluationTests(unittest.TestCase):
    def fixture(self,root):
        data=b'{"predictions":[]}\n';archive=gzip.compress(data,mtime=0);(root/'data.json.gz').write_bytes(archive)
        manifest={'archived_prediction_files':[{'path':'data.json','archive':'data.json.gz','sha256':digest(data),'archive_sha256':digest(archive)}]}
        path=root/'manifest.json';path.write_text(json.dumps(manifest));return path,data

    def test_lossless_restore_and_idempotent_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest,data=self.fixture(root)
            self.assertEqual(restore(manifest,root)['restored'],1)
            self.assertEqual((root/'data.json').read_bytes(),data)
            self.assertEqual(restore(manifest,root)['existing_files_verified'],1)

    def test_differing_destinations_and_tampered_archives_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest,data=self.fixture(root);(root/'data.json').write_bytes(b'local user work')
            with self.assertRaisesRegex(ValueError,'Refusing to overwrite'):restore(manifest,root)
            self.assertEqual((root/'data.json').read_bytes(),b'local user work')
            (root/'data.json').unlink();(root/'data.json.gz').write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):restore(manifest,root)
            self.assertFalse((root/'data.json').exists())


if __name__=='__main__':unittest.main()
