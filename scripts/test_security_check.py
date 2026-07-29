import unittest

from scripts.security_check import ROOT, scan_production_configuration, scan_text


class SecurityCheckTests(unittest.TestCase):
    def test_detects_private_key_material(self):
        path = ROOT / "fixture.txt"
        marker = "-----BEGIN " + "PRIVATE KEY-----"
        findings = scan_text(path, f"{marker}\nnot-a-real-key")
        self.assertTrue(any("private key" in finding for finding in findings))

    def test_detects_secret_assignment_in_configuration(self):
        path = ROOT / "settings.env"
        findings = scan_text(path, "SERVICE_TOKEN=real-looking-value")
        self.assertTrue(any("hard-coded secret assignment" in finding for finding in findings))

    def test_allows_explicit_placeholders(self):
        path = ROOT / "settings.env"
        findings = scan_text(path, "SERVICE_TOKEN=replace-with-test-token")
        self.assertEqual(findings, [])

    def test_does_not_treat_runtime_variable_names_as_values(self):
        path = ROOT / "config.py"
        findings = scan_text(path, 'token = os.environ.get("SERVICE_TOKEN")')
        self.assertEqual(findings, [])

    def test_insecure_production_cookie_is_rejected(self):
        path = ROOT / "production.env"
        findings = scan_production_configuration(path, "TWE_COOKIE_SECURE=false")
        self.assertEqual(len(findings), 1)

    def test_secure_production_cookie_is_allowed(self):
        path = ROOT / "production.env"
        findings = scan_production_configuration(path, "TWE_COOKIE_SECURE=true")
        self.assertEqual(findings, [])

    def test_debug_mode_is_rejected(self):
        path = ROOT / "railway.env"
        findings = scan_production_configuration(path, "FLASK_DEBUG=1")
        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()
