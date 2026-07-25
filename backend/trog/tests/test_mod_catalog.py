import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.mod_catalog import AsaModCatalog, ModResolutionError


class _Lookup:
    def __init__(self, names):
        self.names = names
        self.calls = []

    def names_for(self, mod_ids):
        self.calls.append(mod_ids)
        return {mod_id: self.names[mod_id] for mod_id in mod_ids if mod_id in self.names}

    def search_exact(self, name):
        self.calls.append(("search", name))
        matches = [
            {"id": mod_id, "name": mod_name}
            for mod_id, mod_name in self.names.items()
            if mod_name.casefold() == name.casefold()
        ]
        if not matches:
            raise ModResolutionError("not found")
        return matches[0]


class AsaModCatalogTests(unittest.TestCase):
    def test_shared_catalog_names_the_new_genesis_mod(self):
        catalog = AsaModCatalog(ROOT / "data" / "asa_mod_catalog.json")

        self.assertEqual(
            catalog.enrich([{"id": "930381", "name": "Mod 930381"}]),
            [{"id": "930381", "name": "Silent Structures"}],
        )

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

    def test_resolves_new_numeric_id_and_persists_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asa_mod_catalog.json"
            path.write_text('{"mods": []}')
            catalog = AsaModCatalog(path, _Lookup({"930381": "Silent Structures"}))

            self.assertEqual(
                catalog.resolve("930381"),
                {"id": "930381", "name": "Silent Structures"},
            )
            self.assertIn(
                {"id": "930381", "name": "Silent Structures"},
                json.loads(path.read_text())["mods"],
            )

    def test_resolves_exact_name_to_id_and_persists_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asa_mod_catalog.json"
            path.write_text('{"mods": []}')
            lookup = _Lookup({"930381": "Silent Structures"})
            catalog = AsaModCatalog(path, lookup)

            self.assertEqual(
                catalog.resolve("Silent Structures"),
                {"id": "930381", "name": "Silent Structures"},
            )
            self.assertEqual(lookup.calls, [("search", "Silent Structures")])
            self.assertIn(
                {"id": "930381", "name": "Silent Structures"},
                json.loads(path.read_text())["mods"],
            )

    def test_resolves_name_from_shared_catalog_without_external_search(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asa_mod_catalog.json"
            path.write_text(json.dumps({"mods": [{"id": "930381", "name": "Silent Structures"}]}))
            lookup = _Lookup({})
            catalog = AsaModCatalog(path, lookup)

            self.assertEqual(
                catalog.resolve("silent-structures"),
                {"id": "930381", "name": "Silent Structures"},
            )
            self.assertEqual(lookup.calls, [])


if __name__ == "__main__":
    unittest.main()
