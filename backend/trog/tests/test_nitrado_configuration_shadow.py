import unittest
from unittest.mock import patch

from scripts.verify_nitrado_configuration_shadow import (
    _expected_settings,
    build_shadow_report,
)
from twe.services.provider_contracts import (
    ProviderConfigurationArtifact,
    ProviderConfigurationSnapshot,
    ProviderSetting,
    ProviderSettingsSnapshot,
)


class NitradoConfigurationShadowTests(unittest.TestCase):
    def test_reports_only_expected_explicit_values_and_artifact_metadata(self):
        report = build_shadow_report(
            ProviderSettingsSnapshot(
                settings=(
                    ProviderSetting("saved.settings.CraftXPMultiplier", "1"),
                    ProviderSetting("saved.settings.ServerAdminPassword", "hidden"),
                ),
                checked_at="2026-08-03T12:00:00Z",
            ),
            ProviderConfigurationSnapshot(
                artifacts=(
                    ProviderConfigurationArtifact(
                        source_locator="/ark/config/Game.ini",
                        content=(
                            b"[ServerSettings]\nKillXPMultiplier=5\n"
                            b"HarvestXPMultiplier=3.0\nCraftXPMultiplier=5\n"
                            b"ServerAdminPassword=hidden\n"
                        ),
                        retrieved_at="2026-08-03T12:00:00Z",
                    ),
                ),
                checked_at="2026-08-03T12:00:00Z",
            ),
            {
                "KillXPMultiplier": "5",
                "HarvestXPMultiplier": "3.0",
                "CraftXPMultiplier": "5",
            },
        )

        self.assertTrue(report["ok"])
        self.assertEqual(report["artifact_count"], 1)
        self.assertEqual(report["artifacts"][0]["name"], "Game.ini")
        self.assertEqual(report["comparisons"]["CraftXPMultiplier"]["value"], "5")
        self.assertEqual(report["redacted_sensitive_assignment_count"], 1)
        rendered = str(report)
        self.assertNotIn("hidden", rendered)
        self.assertNotIn("/ark/config/", rendered)

    def test_conflict_fails_closed_without_returning_values(self):
        report = build_shadow_report(
            ProviderSettingsSnapshot((), "2026-08-03T12:00:00Z"),
            ProviderConfigurationSnapshot(
                artifacts=(ProviderConfigurationArtifact(
                    source_locator="/Game.ini",
                    content=b"[ServerSettings]\nCraftXPMultiplier=5\nCraftXPMultiplier=7\n",
                    retrieved_at="2026-08-03T12:00:00Z",
                ),),
                checked_at="2026-08-03T12:00:00Z",
            ),
            {"CraftXPMultiplier": "5"},
        )

        self.assertFalse(report["ok"])
        comparison = report["comparisons"]["CraftXPMultiplier"]
        self.assertEqual(comparison["state"], "conflicted")
        self.assertIsNone(comparison["value"])

    def test_expected_settings_reject_sensitive_keys(self):
        with patch.dict(
            "os.environ",
            {"TWE_SHADOW_EXPECTED_SETTINGS_JSON": '{"ServerAdminPassword":"hidden"}'},
        ):
            with self.assertRaisesRegex(ValueError, "non-sensitive"):
                _expected_settings()


if __name__ == "__main__":
    unittest.main()
