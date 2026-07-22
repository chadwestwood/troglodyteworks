import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "production_smoke.py"
SPEC = importlib.util.spec_from_file_location("production_smoke", SCRIPT)
production_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_smoke)


class ProductionSmokeTests(unittest.TestCase):
    @patch.object(production_smoke, "fetch")
    def test_expected_public_contracts_pass(self, fetch_mock):
        fetch_mock.side_effect = [
            (200, "application/json", b'{"status":"ok"}'),
            (200, "text/html; charset=utf-8", b"<html>home</html>"),
            (200, "text/html; charset=utf-8", b"<html>sign in</html>"),
            (401, "application/json", b'{"error":{"code":"UNAUTHENTICATED"}}'),
        ]

        results = production_smoke.run_checks("https://example.test")

        self.assertTrue(all(result.passed for result in results))
        self.assertEqual(fetch_mock.call_count, 4)

    @patch.object(production_smoke, "fetch")
    def test_failures_do_not_include_response_body(self, fetch_mock):
        secret_like_body = json.dumps({"token": "must-not-be-printed"}).encode()
        fetch_mock.return_value = (500, "application/json", secret_like_body)

        results = production_smoke.run_checks("https://example.test")

        self.assertTrue(all(not result.passed for result in results))
        self.assertNotIn("must-not-be-printed", " ".join(result.detail for result in results))


if __name__ == "__main__":
    unittest.main()
