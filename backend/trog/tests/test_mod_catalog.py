import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.mod_catalog import AsaModCatalog


class _Lookup:
    def __init__(self, names):
        self.names = names
        self.calls = []

    def names_for(self, mod_ids):
        self.calls.append(mod_ids)
        return {mod_id: self.names[mod_id] for mod_id in mod_ids if mod_id in self.names}


class AsaModCatalogTests(unittest.TestCase):
    def test_reads_shared_names_and_resolves_then_persists_new_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asa_mod_catalog.json"
            path.write_text(json.dumps({"mods": [{"id": "111", "name": "Known Mod"}]}))
            lookup = _Lookup({"222": "New Global Mod"})
            catalog = AsaModCatalog(path, lookup)

            mods = catalog.enrich([
                {"id": "111", "name": "Mod 111"},
                {"id": "222", "name": "Mod 222"},
            ])

            self.assertEqual(mods, [
                {"id": "111", "name": "Known Mod"},
                {"id": "222", "name": "New Global Mod"},
            ])
            self.assertEqual(lookup.calls, [("222",)])
            saved = json.loads(path.read_text())
            self.assertIn({"id": "222", "name": "New Global Mod"}, saved["mods"])

    def test_provider_names_update_the_global_catalog_without_external_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asa_mod_catalog.json"
            path.write_text('{"mods": []}')
            catalog = AsaModCatalog(path)

            self.assertEqual(
                catalog.enrich([{"id": "333", "name": "Provider Name"}]),
                [{"id": "333", "name": "Provider Name"}],
            )
            self.assertEqual(json.loads(path.read_text())["mods"], [
                {"id": "333", "name": "Provider Name"},
            ])


if __name__ == "__main__":
    unittest.main()
