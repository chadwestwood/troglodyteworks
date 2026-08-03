import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, patch

from twe.services.provider_contracts import (
    ProviderConfigurationArtifact,
    ProviderConfigurationSnapshot,
    ProviderConnectionRecord,
    ProviderContext,
    ProviderResourceRecord,
    ProviderSetting,
    ProviderSettingsSnapshot,
    TimeoutPolicy,
)
from twe.services.world_configuration_registry import (
    load_verified_world_configuration,
    store_verified_world_configuration,
)
from twe.discord_bot.service import _relevant_provider_settings


class _NoSecret:
    def read_envelope(self):
        raise AssertionError("Registry storage must not read provider credentials.")


def _context():
    return ProviderContext(
        connection=ProviderConnectionRecord(
            id="connection-a",
            community_id="community-a",
            provider_key="nitrado",
            display_name="Nitrado A",
            auth_strategy="configuration",
            external_account_id=None,
            status="active",
        ),
        resource=ProviderResourceRecord(
            id="resource-a",
            provider_connection_id="connection-a",
            resource_type="game_server_service",
            external_resource_id="19592191",
            display_name="Genesis",
            provider_game_key="ark_survival_ascended",
            normalized_status="online",
            provider_status="started",
        ),
        secret_accessor=_NoSecret(),
        correlation_id="correlation-a",
        timeout_policy=TimeoutPolicy(),
    )


class WorldConfigurationRegistryTests(unittest.TestCase):
    @patch("twe.services.world_configuration_registry.load_verified_world_configuration")
    @patch("twe.services.world_configuration_registry.execute")
    @patch("twe.services.world_configuration_registry.fetch_one")
    def test_store_uses_instance_and_resolved_provider_lineage_only(
        self, fetch_one, execute, load_verified,
    ):
        fetch_one.return_value = None
        expected = ProviderSettingsSnapshot((), "2026-08-03T10:00:00Z")
        load_verified.return_value = expected
        settings = ProviderSettingsSnapshot(
            (ProviderSetting("saved.settings.CraftXPMultiplier", "1"),),
            "2026-08-03T10:00:00Z",
        )
        configuration = ProviderConfigurationSnapshot(
            artifacts=(ProviderConfigurationArtifact(
                source_locator="/ark/ShooterGame/Saved/Config/LinuxServer/Game.ini",
                content=b"[/Script/ShooterGame.ShooterGameMode]\nCraftXPMultiplier=5\n",
                retrieved_at="2026-08-03T10:00:00Z",
            ),),
            checked_at="2026-08-03T10:00:00Z",
        )

        result = store_verified_world_configuration(
            object(),
            game_instance_id="world-a",
            provider_context=_context(),
            settings_snapshot=settings,
            configuration_snapshot=configuration,
        )

        self.assertIs(result, expected)
        revision_params = execute.call_args_list[0].args[2]
        self.assertEqual(revision_params[1:6], (
            "world-a", "resource-a", "connection-a", "nitrado", "19592191",
        ))
        for call in execute.call_args_list:
            query, params = call.args[1:3]
            if "world_configuration_" in query:
                self.assertIn("world-a", params)
        load_verified.assert_called_once_with(ANY, "world-a")

    @patch("twe.services.world_configuration_registry.fetch_all")
    @patch("twe.services.world_configuration_registry.fetch_one")
    def test_load_is_exact_instance_scoped_and_excludes_conflicting_duplicates(
        self, fetch_one, fetch_all,
    ):
        fetch_one.return_value = {
            "id": "revision-a",
            "observed_at": datetime(2026, 8, 3, 10, tzinfo=timezone.utc),
        }
        fetch_all.return_value = [
            {
                "source_role": "saved_ini",
                "source_locator": "/Game.ini",
                "source_section": "ServerSettings",
                "source_key": "CraftXPMultiplier",
                "occurrence_index": 0,
                "raw_value": "5",
            },
            {
                "source_role": "saved_ini",
                "source_locator": "/Game.ini",
                "source_section": "ServerSettings",
                "source_key": "CraftXPMultiplier",
                "occurrence_index": 1,
                "raw_value": "7",
            },
            {
                "source_role": "saved_ini",
                "source_locator": "/GameUserSettings.ini",
                "source_section": "ServerSettings",
                "source_key": "KillXPMultiplier",
                "occurrence_index": 0,
                "raw_value": "5",
            },
            {
                "source_role": "provider_settings",
                "source_locator": "nitrado:gameservers/settings",
                "source_section": None,
                "source_key": "saved.settings.CraftXPMultiplier",
                "occurrence_index": 0,
                "raw_value": "1",
            },
        ]

        snapshot = load_verified_world_configuration(object(), "world-a")

        self.assertEqual(fetch_one.call_args.args[2], ("world-a",))
        self.assertEqual(fetch_all.call_args.args[2], ("revision-a", "world-a"))
        self.assertEqual(len(snapshot.settings), 1)
        self.assertIn("KillXPMultiplier", snapshot.settings[0].path)
        self.assertEqual(snapshot.settings[0].value, "5")

    @patch("twe.services.world_configuration_registry.fetch_all")
    @patch("twe.services.world_configuration_registry.fetch_one")
    def test_saved_ini_value_outranks_provider_summary_value(
        self, fetch_one, fetch_all,
    ):
        fetch_one.return_value = {
            "id": "revision-a",
            "observed_at": datetime(2026, 8, 3, 10, tzinfo=timezone.utc),
        }
        fetch_all.return_value = [
            {
                "source_role": "provider_settings",
                "source_locator": "nitrado:gameservers/settings",
                "source_section": None,
                "source_key": "saved.settings.CraftXPMultiplier",
                "occurrence_index": 0,
                "raw_value": "1",
            },
            {
                "source_role": "saved_ini",
                "source_locator": "/Game.ini",
                "source_section": "ServerSettings",
                "source_key": "CraftXPMultiplier",
                "occurrence_index": 0,
                "raw_value": "5",
            },
        ]

        snapshot = load_verified_world_configuration(object(), "world-a")
        relevant = _relevant_provider_settings(
            "What is the current craft XP multiplier?",
            snapshot.settings,
        )

        self.assertEqual(len(relevant), 1)
        self.assertEqual(relevant[0].path, "CraftXPMultiplier")
        self.assertEqual(relevant[0].value, "5")


if __name__ == "__main__":
    unittest.main()
