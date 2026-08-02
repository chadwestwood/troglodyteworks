import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from twe.services.provider_contracts import ProviderSetting, ProviderSettingsSnapshot
from twe.services.world_configuration import (
    load_world_configuration_snapshot,
    sanitize_world_settings,
    store_world_configuration_snapshot,
)


class WorldConfigurationTests(unittest.TestCase):
    def test_sanitize_removes_sensitive_settings(self):
        settings = (
            ProviderSetting(path="settings.gameini.HarvestAmountMultiplier", value=3),
            ProviderSetting(path="settings.config.ServerPassword", value="hidden"),
            ProviderSetting(path="api_key", value="hidden"),
            ProviderSetting(path="WebhookSecret", value="hidden"),
        )

        safe = sanitize_world_settings(settings)

        self.assertEqual(len(safe), 1)
        self.assertEqual(safe[0].path, "settings.gameini.HarvestAmountMultiplier")
        self.assertEqual(safe[0].value, "3")

    @patch("twe.services.world_configuration.fetch_one")
    def test_load_returns_latest_sanitized_snapshot(self, fetch_one):
        checked_at = datetime(2026, 8, 1, 12, 30, tzinfo=timezone.utc)
        fetch_one.return_value = {
            "settings": json.dumps(
                [
                    {"path": "settings.gameini.MatingIntervalMultiplier", "value": "0.25"},
                    {"path": "settings.config.AdminPassword", "value": "hidden"},
                ]
            ),
            "checked_at": checked_at,
        }

        snapshot = load_world_configuration_snapshot(object(), "world-1")

        self.assertEqual(snapshot.checked_at, checked_at.isoformat())
        self.assertEqual(
            snapshot.settings,
            (ProviderSetting(path="settings.gameini.MatingIntervalMultiplier", value="0.25"),),
        )
        fetch_one.assert_called_once()

    @patch("twe.services.world_configuration.execute")
    def test_store_persists_only_safe_settings(self, execute):
        snapshot = ProviderSettingsSnapshot(
            settings=(
                ProviderSetting(path="settings.gameini.EggHatchSpeedMultiplier", value="5"),
                ProviderSetting(path="settings.config.ServerPassword", value="hidden"),
            ),
            checked_at="2026-08-01T12:30:00+00:00",
        )

        stored = store_world_configuration_snapshot(
            object(),
            game_instance_id="world-1",
            provider_key="nitrado",
            source_kind="provider_pull",
            snapshot=snapshot,
        )

        self.assertEqual(len(stored.settings), 1)
        parameters = execute.call_args.args[2]
        payload = json.loads(parameters[4])
        self.assertEqual(
            payload,
            [{"path": "settings.gameini.EggHatchSpeedMultiplier", "value": "5"}],
        )
        self.assertNotIn("hidden", parameters[4])


if __name__ == "__main__":
    unittest.main()
