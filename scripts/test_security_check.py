import unittest

from scripts.security_check import ROOT, scan_text


class SecurityCheckTests(unittest.TestCase):
    def test_detects_private_key_material(self):
        path = ROOT / "fixture.txt"
        findings = scan_text(path, "-----BEGIN PRIVATE KEY-----\nnot-a-real-key")
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


if __name__ == "__main__":
    unittest.main()
