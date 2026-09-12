"""Recording must fail before rendering stale or altered sponsor artwork."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flyhard.live_livery import verify_live_livery, verify_layer_livery


class LiveLiveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / 'asset'; self.asset.mkdir()
        self.manifest = {'revision': 12, 'layoutVersion': 4,
                         'sponsors': [{'slotId': 'ad-01', 'texture': 'ad-01.png'}]}
        (self.asset / 'manifest.json').write_text(json.dumps(self.manifest))
        (self.asset / 'ad-01.png').write_bytes(b'original paid artwork')
        self.hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in self.asset.iterdir()}
        self.hashes['sponsored-mini.blend'] = 'model-hash'
        (self.asset / 'sha256.json').write_text(json.dumps(self.hashes))
        self.live = {'revision': 12, 'placements': {'ad-01': {}}}
        self.layout = {'layout_version': 4}

    def check(self):
        responses = [io.BytesIO(json.dumps(x).encode()) for x in [self.live, self.layout]]
        with patch('flyhard.live_livery.urllib.request.urlopen', side_effect=responses):
            return verify_live_livery(self.asset, self.root / 'run')

    def test_current_snapshot_writes_evidence(self):
        self.assertEqual(self.check()['revision'], 12)
        receipt = json.loads((self.root / 'run/livery-preflight.json').read_text())
        self.assertEqual(receipt['verified_files']['ad-01.png'], self.hashes['ad-01.png'])

    def test_changed_live_revision_blocks_run(self):
        self.live['revision'] = 13
        with self.assertRaisesRegex(RuntimeError, 'Sponsors changed'): self.check()
        self.assertFalse((self.root / 'run').exists())

    def test_missing_paid_surface_blocks_run(self):
        self.live['placements']['ad-02'] = {}
        with self.assertRaisesRegex(RuntimeError, 'paid sponsor surfaces'): self.check()

    def test_modified_artwork_blocks_run(self):
        (self.asset / 'ad-01.png').write_bytes(b'changed artwork')
        with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'): self.check()

    def test_changed_layout_blocks_run(self):
        self.layout['layout_version'] = 5
        with self.assertRaisesRegex(RuntimeError, 'layout changed'): self.check()

    def test_cached_projection_must_match_model(self):
        layers = self.root / 'layers'; layers.mkdir()
        (layers / 'metrics.json').write_text(json.dumps({'revision': 12, 'layout': 4, 'source_blend_sha256': 'older-model'}))
        with self.assertRaisesRegex(RuntimeError, 'packed model'):
            verify_layer_livery(self.asset, layers)


if __name__ == '__main__': unittest.main()
