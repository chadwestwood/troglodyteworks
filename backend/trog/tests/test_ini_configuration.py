import unittest

from twe.services.ini_configuration import parse_ini


class IniConfigurationTests(unittest.TestCase):
    def test_preserves_all_explicit_assignments_and_duplicates_without_defaults(self):
        parsed = parse_ini(
            """[ServerSettings]
KillXPMultiplier=5
HarvestXPMultiplier=3.0
CraftXPMultiplier=5
CraftXPMultiplier=7
"""
        )

        self.assertEqual(len(parsed.observations), 4)
        self.assertEqual(parsed.observations[0].typed_value, 5)
        self.assertEqual(parsed.observations[1].typed_value, 3.0)
        self.assertEqual(parsed.observations[2].occurrence_index, 0)
        self.assertEqual(parsed.observations[3].occurrence_index, 1)
        self.assertFalse(any(item.source_key == "default" for item in parsed.observations))

    def test_redacts_sensitive_values_before_persistence(self):
        parsed = parse_ini(
            "[ServerSettings]\nServerAdminPassword=secret\nRCONPort=27020\n"
        )

        password, rcon = parsed.observations
        self.assertTrue(password.is_sensitive)
        self.assertIsNone(password.raw_value)
        self.assertIsNone(password.typed_value)
        self.assertFalse(rcon.is_sensitive)
        self.assertEqual(rcon.typed_value, 27020)
        self.assertNotIn("secret", repr(parsed))

    def test_records_unparsed_lines_without_inventing_a_value(self):
        parsed = parse_ini("[ServerSettings]\nnot an assignment\nCraftXPMultiplier=5\n")

        self.assertEqual(len(parsed.diagnostic_line_hashes), 1)
        self.assertEqual(len(parsed.observations), 1)
        self.assertEqual(parsed.observations[0].raw_value, "5")


if __name__ == "__main__":
    unittest.main()
