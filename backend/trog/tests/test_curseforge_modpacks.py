import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.curseforge_modpacks import CurseForgeModpacks, CurseForgeUnavailable


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self._body = BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount):
        return self._body.read(amount)


class CurseForgeModpackTests(unittest.TestCase):
    @patch("twe.services.curseforge_modpacks.urlopen")
    def test_search_filters_and_sanitizes_modpacks(self, opener):
        opener.return_value = FakeResponse({"data": [
            {"id": 123, "name": "Pack", "slug": "pack", "summary": "A pack", "isAvailable": True,
             "downloadCount": 42, "logo": {"thumbnailUrl": "https://example.test/logo.png"}},
            {"id": 456, "name": "Gone", "isAvailable": False},
        ]})
        rows = CurseForgeModpacks("https://api.example", "secret").search("pack")
        self.assertEqual(rows, [{"id": 123, "name": "Pack", "summary": "A pack", "slug": "pack",
                                 "logo_url": "https://example.test/logo.png", "download_count": 42}])
        request = opener.call_args.args[0]
        self.assertNotIn("secret", request.full_url)
        self.assertEqual(request.headers["X-api-key"], "secret")

    @patch("twe.services.curseforge_modpacks.urlopen")
    def test_invalid_response_is_provider_error(self, opener):
        opener.return_value = FakeResponse([])
        with self.assertRaises(CurseForgeUnavailable):
            CurseForgeModpacks("https://api.example", "secret").search("pack")


if __name__ == "__main__":
    unittest.main()
