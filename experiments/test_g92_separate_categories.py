import json
from pathlib import Path
import tempfile
import unittest

from experiments.g89_semantic_categories import read_data, ROOT


class SeparateSourceTests(unittest.TestCase):
    def test_manifest_parameter_preserves_reader_and_rejects_changed_source(self):
        original = ROOT/'results_v3/g89_source_manifest.json'
        self.assertEqual(read_data('esp.train.gz'),
                         read_data('esp.train.gz', manifest_path=original))
        manifest = json.loads(original.read_text())
        for entry in manifest['files']:
            if entry['name'] == 'esp.train.gz':
                entry['compressed_sha256'] = '0'*64
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'manifest.json'
            path.write_text(json.dumps(manifest))
            with self.assertRaises(AssertionError):
                read_data('esp.train.gz', manifest_path=path)


if __name__ == '__main__':
    unittest.main()
