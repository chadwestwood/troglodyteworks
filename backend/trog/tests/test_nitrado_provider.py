import json
import socket
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.services.nitrado_provider import (
    NitradoAuthenticationError,
    NitradoHttpResponse,
    NitradoHttpTransport,
    NitradoInsufficientScopeError,
    NitradoMalformedResponseError,
    NitradoProvider,
    NitradoRateLimitedError,
    NitradoSettingsVerificationError,
    NitradoUnavailableError,
)
from twe.services.provider_contracts import (
    BoundSecretAccessor,
    ProviderConnectionRecord,
    ProviderContext,
    ProviderResourceRecord,
    ProviderSecretEnvelope,
    TimeoutPolicy,
)
from twe.services.provider_secret_storage import AesGcmProviderSecretCipher


class _Transport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, headers, timeout_seconds):
        self.calls.append((url, headers, timeout_seconds))
        if self.error:
            raise self.error
        return self._next_response()

    def post(self, url, headers, form, timeout_seconds):
        self.calls.append((url, headers, form, timeout_seconds))
        if self.error:
            raise self.error
        return self._next_response()

    def _next_response(self):
        if isinstance(self.response, list):
            return self.response.pop(0)
        return self.response


def _response(services):
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({"status": "success", "data": {"services": services}}).encode(),
    )


def _gameserver_response(status):
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({
            "status": "success",
            "data": {
                "gameserver": {
                    "status": status,
                    "websocket_token": "must-not-survive",
                    "credentials": {"password": "must-not-survive"},
                },
            },
        }).encode(),
    )


def _gameserver_players_response(players):
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({
            "status": "success",
            "data": {"players": players},
        }).encode(),
    )


def _gameserver_mods_response(mods):
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({
            "status": "success",
            "data": {"gameserver": {"settings": {"general": {"activeMods": mods}}}},
        }).encode(),
    )


def _gameserver_settings_response(*, nested=True):
    settings = {
        "general": {
            "PlayerHarvestingDamageMultiplier": {"value": 3, "default": 1},
            "HarvestXPMultiplier": {"current": 3.0, "default": 1.0},
            "ServerAdminPassword": "must-not-survive",
            "RCONPort": 11550,
        },
    }
    data = {"gameserver": {"settings": settings}} if nested else {"settings": settings}
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({
            "status": "success",
            "data": data,
        }).encode(),
    )


class NitradoProviderTests(unittest.TestCase):
    def setUp(self):
        self.key = b"k" * 32
        self.config = Config(
            database_url="postgresql://unused",
            provider_secret_keys={"key-1": self.key},
            provider_secret_active_key_version="key-1",
        )

    def _context(self, credential=b"secret-token", expires_at=None):
        cipher = AesGcmProviderSecretCipher({"key-1": self.key}, "key-1")
        encrypted, nonce, version = cipher.encrypt("connection-id", credential)
        return ProviderContext(
            connection=ProviderConnectionRecord(
                id="connection-id",
                community_id="community-id",
                provider_key="nitrado",
                display_name="Nitrado",
                auth_strategy="configuration",
                external_account_id=None,
                status="active",
            ),
            resource=ProviderResourceRecord(
                id="resource-id",
                provider_connection_id="connection-id",
                resource_type="game_server_service",
                external_resource_id="42",
                display_name="Genesis",
                provider_game_key="ark_survival_ascended",
                normalized_status="unknown",
                provider_status="unknown",
            ),
            secret_accessor=BoundSecretAccessor(ProviderSecretEnvelope(
                storage_kind="encrypted_payload",
                encrypted_payload=encrypted,
                encryption_nonce=nonce,
                key_version=version,
                expires_at=expires_at,
            )),
            correlation_id="correlation-id",
            timeout_policy=TimeoutPolicy(),
        )

    def test_uses_services_endpoint_authorization_header_and_service_scope_only(self):
        transport = _Transport(_response([]))
        provider = NitradoProvider(self.config, transport)

        validation = provider.validate_credential(b"secret-token")

        self.assertEqual(validation.granted_scopes, ("service",))
        self.assertEqual(transport.calls[0][0], "https://api.nitrado.net/services")
        self.assertEqual(transport.calls[0][1]["Authorization"], "Bearer secret-token")
        self.assertNotIn("secret-token", transport.calls[0][0])
        self.assertEqual(transport.calls[0][2], 8.0)

    def test_normalizes_supported_asa_and_separates_unsupported_and_omitted_services(self):
        transport = _Transport(_response([
            {
                "id": 42, "type": "gameserver", "status": "active",
                "type_human": "Gameserver 20 Slots", "location_id": 2,
                "suspend_date": "2026-08-01T00:00:00",
                "details": {
                    "name": "Cave Friends", "game": "ARK: Survival Ascended",
                    "folder_short": "provider-key-not-assumed", "game_slots": 20,
                    "address": "203.0.113.10:7777",
                },
                "websocket_token": "must-not-survive",
            },
            {
                "id": 43, "type": "gameserver", "status": "suspended",
                "details": {"name": "Old ARK", "game": "ARK: Survival Evolved", "slots": 10},
            },
            {"id": 44, "type": "voiceserver", "status": "active"},
            {"id": 42, "type": "gameserver", "status": "active", "details": {}},
        ]))

        result = NitradoProvider(self.config, transport).discover_resources_with_credential(b"token")

        self.assertEqual(result.total_services, 4)
        self.assertEqual(result.unsupported_services, 1)
        self.assertEqual(result.omitted_services, 1)
        self.assertEqual(len(result.resources), 2)
        supported = result.resources[0]
        self.assertEqual(supported.external_resource_id, "42")
        self.assertEqual(supported.provider_game_key, "ark_survival_ascended")
        self.assertEqual(supported.metadata["slots"], 20)
        self.assertNotIn("websocket_token", supported.metadata)
        self.assertNotIn("must-not-survive", repr(supported))
        self.assertIsNone(result.resources[1].provider_game_key)
        self.assertEqual(result.resources[1].normalized_status, "offline")

    def test_reads_live_gameserver_status_with_decrypted_bound_credential(self):
        transport = _Transport(_gameserver_response("started"))

        status = NitradoProvider(self.config, transport).read_status(self._context())

        self.assertEqual(status.normalized_status, "online")
        self.assertEqual(status.provider_status, "ready")
        self.assertEqual(status.as_health_payload()["overall_status"], "ready")
        self.assertEqual(
            transport.calls[0][0],
            "https://api.nitrado.net/services/42/gameservers",
        )
        self.assertEqual(transport.calls[0][1]["Authorization"], "Bearer secret-token")
        rendered = repr(status)
        self.assertNotIn("secret-token", rendered)
        self.assertNotIn("must-not-survive", rendered)

    def test_reads_live_player_names_from_dedicated_player_endpoint(self):
        transport = _Transport(_gameserver_players_response([
            {"name": "Chad", "id": 1, "bot": False, "online": "true"},
            {"name": "Helper Bot", "id": 2, "bot": True},
            {"name": "Former Player", "id": 3, "bot": False, "online": "false"},
            {"name": "Cave Friend", "id": 4, "bot": False},
        ]))

        players = NitradoProvider(self.config, transport).read_players(self._context())

        self.assertEqual(players, {"players": ["Chad", "Cave Friend"]})
        self.assertEqual(
            transport.calls[0][0],
            "https://api.nitrado.net/services/42/gameservers/games/players",
        )
        self.assertNotIn("secret-token", repr(players))

    def test_player_read_rejects_missing_player_data(self):
        provider = NitradoProvider(
            self.config,
            _Transport(_gameserver_response("started")),
        )

        with self.assertRaises(NitradoMalformedResponseError):
            provider.read_players(self._context())

    def test_reads_active_mods_from_gameserver_settings_in_load_order(self):
        transport = _Transport(_gameserver_mods_response("927090, 928708,927090"))

        mods = NitradoProvider(self.config, transport).read_mods(self._context())

        self.assertEqual(mods, [
            {"id": "927090", "name": "Mod 927090"},
            {"id": "928708", "name": "Mod 928708"},
        ])
        self.assertEqual(
            transport.calls[0][0],
            "https://api.nitrado.net/services/42/gameservers",
        )

    def test_reads_provider_supplied_mod_names(self):
        transport = _Transport(_gameserver_mods_response([
            {"project_id": 927090, "title": "Awesome SpyGlass"},
            {"id": "928708", "name": "Dino Depot"},
        ]))

        mods = NitradoProvider(self.config, transport).read_mods(self._context())

        self.assertEqual(mods[0], {"id": "927090", "name": "Awesome SpyGlass"})
        self.assertEqual(mods[1], {"id": "928708", "name": "Dino Depot"})

    def test_reads_sanitized_explicit_settings_from_gameserver(self):
        transport = _Transport(_gameserver_settings_response(nested=False))

        snapshot = NitradoProvider(self.config, transport).read_settings(self._context())

        self.assertEqual(
            transport.calls[0][0],
            "https://api.nitrado.net/services/42/gameservers/settings",
        )
        self.assertEqual(len(transport.calls), 1)
        values = {setting.path: setting.value for setting in snapshot.settings}
        self.assertEqual(
            values["saved.settings.general.PlayerHarvestingDamageMultiplier"],
            "3",
        )
        self.assertEqual(values["saved.settings.general.HarvestXPMultiplier"], "3.0")
        rendered = repr(snapshot)
        self.assertNotIn("ServerAdminPassword", rendered)
        self.assertNotIn("RCONPort", rendered)
        self.assertNotIn("must-not-survive", rendered)
        self.assertNotIn("secret-token", rendered)

    def test_reads_named_setting_rows_without_using_defaults(self):
        transport = _Transport(NitradoHttpResponse(
            status=200,
            body=json.dumps({
                "status": "success",
                "data": {"settings": [
                    {"key": "MatingIntervalMultiplier", "value": "0.125", "default": "1.0"},
                    {"name": "EggHatchSpeedMultiplier", "current": 25, "default": 1},
                    {"key": "ServerAdminPassword", "value": "must-not-survive"},
                ]},
            }).encode(),
        ))

        snapshot = NitradoProvider(self.config, transport).read_settings(self._context())

        values = {setting.path: setting.value for setting in snapshot.settings}
        self.assertEqual(values["saved.settings.MatingIntervalMultiplier"], "0.125")
        self.assertEqual(values["saved.settings.EggHatchSpeedMultiplier"], "25")
        self.assertNotIn("ServerAdminPassword", repr(snapshot))

    def test_ignores_game_specific_form_defaults_when_saved_settings_exist(self):
        transport = _Transport(NitradoHttpResponse(
            status=200,
            body=json.dumps({
                "status": "success",
                "data": {
                    "settings": {
                        "config": {
                            "game.ini": [
                                "MatingIntervalMultiplier=0.125",
                                "EggHatchSpeedMultiplier=25.0",
                                "BabyMatureSpeedMultiplier=20.0",
                            ],
                        },
                    },
                    "game_specific": {
                        "MatingIntervalMultiplier": {"value": 1.0},
                        "EggHatchSpeedMultiplier": {"value": 1.0},
                        "BabyMatureSpeedMultiplier": {"value": 1.0},
                    },
                },
            }).encode(),
        ))

        snapshot = NitradoProvider(self.config, transport).read_settings(self._context())

        values = {setting.path: setting.value for setting in snapshot.settings}
        self.assertEqual(
            values["saved.settings.config.game.ini.MatingIntervalMultiplier"],
            "0.125",
        )
        self.assertEqual(
            values["saved.settings.config.game.ini.EggHatchSpeedMultiplier"],
            "25.0",
        )
        self.assertNotIn("game_specific", " ".join(values))

    def test_keeps_saved_configuration_after_large_metadata_payload(self):
        settings = {
            "form": {
                f"field_{index}": {"default": 1.0}
                for index in range(260)
            },
            "config": {
                "game.ini": ["MatingIntervalMultiplier=0.25"],
            },
        }
        response = NitradoHttpResponse(
            status=200,
            body=json.dumps({
                "status": "success",
                "data": {"settings": settings},
            }).encode("utf-8"),
        )

        snapshot = NitradoProvider(
            self.config, _Transport(response)
        ).read_settings(self._context())

        values = {setting.path: setting.value for setting in snapshot.settings}
        self.assertEqual(
            values["saved.settings.config.game.ini.MatingIntervalMultiplier"],
            "0.25",
        )
        self.assertEqual(len(snapshot.settings), 1)
        self.assertNotIn("field_", repr(snapshot))

    def test_live_settings_read_rejects_default_only_form_metadata(self):
        response = NitradoHttpResponse(
            status=200,
            body=json.dumps({
                "status": "success",
                "data": {"settings": {
                    "form": {
                        "MatingIntervalMultiplier": {"default": 1.0},
                        "EggHatchSpeedMultiplier": {"default": 1.0},
                    },
                }},
            }).encode("utf-8"),
        )

        with self.assertRaises(NitradoMalformedResponseError):
            NitradoProvider(
                self.config, _Transport(response)
            ).read_settings(self._context())

    def test_live_settings_read_fails_closed_without_a_settings_payload(self):
        provider = NitradoProvider(
            self.config,
            _Transport(_gameserver_response("started")),
        )

        with self.assertRaises(NitradoMalformedResponseError):
            provider.read_settings(self._context())

    def test_reads_all_saved_ini_files_for_the_bound_service_without_leaking_credential(self):
        transport = _Transport([
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"bookmarks": [{"path": "/ark/ShooterGame/Saved/Config/LinuxServer"}]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"entries": [
                    {"name": "Game.ini", "dir": "/ark/ShooterGame/Saved/Config/LinuxServer"},
                    {"name": "GameUserSettings.ini", "dir": "/ark/ShooterGame/Saved/Config/LinuxServer"},
                ]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"token": {"url": "https://fileserver.nitrado.net/download", "token": "one"}},
            }).encode()),
            NitradoHttpResponse(status=200, body=b"[ServerSettings]\nCraftXPMultiplier=5\n"),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"token": {"url": "https://fileserver.nitrado.net/download", "token": "two"}},
            }).encode()),
            NitradoHttpResponse(status=200, body=b"[ServerSettings]\nKillXPMultiplier=5\n"),
        ])

        snapshot = NitradoProvider(self.config, transport).read_configuration(self._context())

        self.assertEqual(len(snapshot.artifacts), 2)
        self.assertTrue(snapshot.artifacts[0].source_locator.endswith("Game.ini"))
        self.assertTrue(snapshot.artifacts[1].source_locator.endswith("GameUserSettings.ini"))
        download_calls = [call for call in transport.calls if call[0].startswith("https://fileserver")]
        self.assertEqual(len(download_calls), 2)
        self.assertTrue(all("Authorization" not in call[1] for call in download_calls))
        self.assertNotIn("secret-token", repr(snapshot))

    def test_reads_string_bookmarks_returned_by_live_nitrado_api(self):
        transport = _Transport([
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"bookmarks": ["/ark/ShooterGame/Saved/Config/LinuxServer"]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"entries": [
                    {"name": "Game.ini", "dir": "/ark/ShooterGame/Saved/Config/LinuxServer"},
                ]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"token": {
                    "url": "https://fileserver.nitrado.net/download",
                    "token": "one",
                }},
            }).encode()),
            NitradoHttpResponse(
                status=200,
                body=b"[ServerSettings]\nCraftXPMultiplier=5\n",
            ),
        ])

        snapshot = NitradoProvider(self.config, transport).read_configuration(
            self._context()
        )

        self.assertEqual(len(snapshot.artifacts), 1)
        self.assertTrue(snapshot.artifacts[0].source_locator.endswith("Game.ini"))
        listing_calls = [
            call for call in transport.calls if "file_server/list" in call[0]
        ]
        self.assertEqual(len(listing_calls), 1)
        self.assertNotIn("search=", listing_calls[0][0])

    def test_rejects_non_nitrado_download_url(self):
        transport = _Transport([
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success", "data": {"bookmarks": [{"path": "/config"}]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success", "data": {"entries": [{"name": "Game.ini", "dir": "/config"}]},
            }).encode()),
            NitradoHttpResponse(status=200, body=json.dumps({
                "status": "success",
                "data": {"token": {"url": "https://example.com/private", "token": "bad"}},
            }).encode()),
        ])

        with self.assertRaises(NitradoMalformedResponseError):
            NitradoProvider(self.config, transport).read_configuration(self._context())

    def test_enriches_ordered_mod_ids_from_nested_provider_metadata(self):
        response = json.dumps({
            "status": "success",
            "data": {
                "gameserver": {
                    "settings": {"general": {"activeMods": "927090,928708"}},
                    "game_specific": {
                        "available": {
                            "mods": [
                                {"id": "928708", "name": "Dino Depot"},
                                {"project_id": 927090, "title": "Winter Wonderland"},
                            ]
                        }
                    },
                }
            },
        }).encode()

        mods = NitradoProvider(self.config, _Transport(NitradoHttpResponse(200, response))).read_mods(
            self._context()
        )

        self.assertEqual(mods, [
            {"id": "927090", "name": "Winter Wonderland"},
            {"id": "928708", "name": "Dino Depot"},
        ])

    def test_discovers_the_servers_exact_writable_mod_setting(self):
        response = NitradoHttpResponse(
            200,
            json.dumps({
                "status": "success",
                "data": {"gameserver": {"settings": {
                    "config": {"active_mods": "927090,928708"},
                }}},
            }).encode(),
        )
        client = NitradoProvider(self.config, _Transport(response))._client

        mods, setting = client.get_gameserver_mod_configuration("42", b"token")

        self.assertEqual([mod["id"] for mod in mods], ["927090", "928708"])
        self.assertEqual(setting, ("config", "active_mods"))

    def test_discovers_an_empty_writable_mod_setting(self):
        response = NitradoHttpResponse(
            200,
            json.dumps({
                "status": "success",
                "data": {"gameserver": {"settings": {
                    "config": {"active_mods": ""},
                }}},
            }).encode(),
        )
        client = NitradoProvider(self.config, _Transport(response))._client

        mods, setting = client.get_gameserver_mod_configuration("42", b"token")

        self.assertEqual(mods, [])
        self.assertEqual(setting, ("config", "active_mods"))

    def test_enriches_nitrado_ids_from_the_shared_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog_path = Path(directory) / "asa_mod_catalog.json"
            catalog_path.write_text(json.dumps({
                "mods": [{"id": "927090", "name": "Global Catalog Name"}],
            }))
            config = replace(self.config, asa_mod_catalog_path=str(catalog_path))

            mods = NitradoProvider(
                config,
                _Transport(_gameserver_mods_response("927090")),
            ).read_mods(self._context())

            self.assertEqual(mods, [{"id": "927090", "name": "Global Catalog Name"}])

    def test_add_mod_preserves_load_order_and_writes_active_mods(self):
        transport = _Transport([
            _gameserver_mods_response("927090,928708"),
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            _gameserver_mods_response("927090,928708,999123"),
        ])
        provider = NitradoProvider(self.config, transport)

        added, mods = provider.add_mod(self._context(), "999123")

        self.assertTrue(added)
        self.assertEqual([mod["id"] for mod in mods], ["927090", "928708", "999123"])
        self.assertEqual(
            transport.calls[1][0],
            "https://api.nitrado.net/services/42/gameservers/settings?category=general&key=activeMods&value=927090%2C928708%2C999123",
        )
        self.assertEqual(transport.calls[1][2], {})

    @patch("twe.services.nitrado_provider.time.sleep", return_value=None)
    def test_add_mod_reapplies_once_when_first_write_is_not_persisted(self, _sleep):
        unchanged = _gameserver_mods_response("927090")
        confirmed = _gameserver_mods_response("927090,999123")
        transport = _Transport([
            unchanged,
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            *[unchanged for _ in range(6)],
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            confirmed,
        ])

        added, mods = NitradoProvider(self.config, transport).add_mod(
            self._context(), "999123",
        )

        self.assertTrue(added)
        self.assertEqual([mod["id"] for mod in mods], ["927090", "999123"])
        settings_calls = [
            call for call in transport.calls
            if "/gameservers/settings?" in call[0]
        ]
        self.assertEqual(len(settings_calls), 2)
        self.assertEqual(settings_calls[0][0], settings_calls[1][0])

    @patch("twe.services.nitrado_provider.time.sleep", return_value=None)
    def test_add_mod_tolerates_temporary_verification_read_failures(self, _sleep):
        transport = _Transport([
            _gameserver_mods_response("927090"),
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            NitradoHttpResponse(503, b""),
            NitradoHttpResponse(429, b""),
            _gameserver_mods_response("927090,999123"),
        ])

        added, mods = NitradoProvider(self.config, transport).add_mod(
            self._context(), "999123",
        )

        self.assertTrue(added)
        self.assertEqual([mod["id"] for mod in mods], ["927090", "999123"])
        settings_calls = [
            call for call in transport.calls
            if "/gameservers/settings?" in call[0]
        ]
        self.assertEqual(len(settings_calls), 1)

    @patch("twe.services.nitrado_provider.time.sleep", return_value=None)
    def test_add_mod_fails_when_nitrado_does_not_confirm_the_setting(self, _sleep):
        unchanged = _gameserver_mods_response("927090")
        transport = _Transport([
            unchanged,
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            *[unchanged for _ in range(6)],
            NitradoHttpResponse(200, b'{"status":"success","data":{}}'),
            *[unchanged for _ in range(6)],
        ])

        with self.assertRaises(NitradoSettingsVerificationError) as raised:
            NitradoProvider(self.config, transport).add_mod(self._context(), "999123")
        self.assertIn("retried it safely", str(raised.exception))
        self.assertIn("server was not restarted", str(raised.exception))

    def test_add_existing_mod_is_idempotent_and_does_not_write(self):
        transport = _Transport(_gameserver_mods_response("927090,928708"))

        added, _mods = NitradoProvider(self.config, transport).add_mod(self._context(), "928708")

        self.assertFalse(added)
        self.assertEqual(len(transport.calls), 1)

    def test_restart_posts_to_nitrado_once(self):
        transport = _Transport(NitradoHttpResponse(200, b'{"status":"success","data":{}}'))

        NitradoProvider(self.config, transport).restart(self._context())

        self.assertEqual(transport.calls[0][0], "https://api.nitrado.net/services/42/gameservers/restart")
        self.assertIn("restart_message", transport.calls[0][2])

    def test_normalizes_gameserver_transitions_without_claiming_ready(self):
        cases = {
            "stopped": "offline",
            "restarting": "degraded",
            "adminlocked": "failed",
            "new-provider-state": "unknown",
        }
        for provider_status, expected in cases.items():
            with self.subTest(provider_status=provider_status):
                status = NitradoProvider(
                    self.config,
                    _Transport(_gameserver_response(provider_status)),
                ).read_status(self._context())
                self.assertEqual(status.provider_status, expected)

    def test_status_read_rejects_expired_or_missing_credentials_before_http(self):
        expired = datetime.now(timezone.utc) - timedelta(seconds=1)
        transport = _Transport(_gameserver_response("started"))
        provider = NitradoProvider(self.config, transport)

        with self.assertRaises(NitradoAuthenticationError):
            provider.read_status(self._context(expires_at=expired))
        self.assertEqual(transport.calls, [])

        context = self._context()
        context = ProviderContext(
            connection=context.connection,
            resource=context.resource,
            secret_accessor=BoundSecretAccessor(),
            correlation_id=context.correlation_id,
            timeout_policy=context.timeout_policy,
        )
        with self.assertRaises(NitradoAuthenticationError):
            provider.read_status(context)
        self.assertEqual(transport.calls, [])

    def test_status_read_rejects_malformed_or_ambiguous_gameserver_payload(self):
        bodies = (
            b'{"status":"success","data":{"gameserver":{}}}',
            b'{"status":"success","data":{"gameservers":[]}}',
            b'{"status":"success","data":{"gameservers":[{"status":"started"},{"status":"stopped"}]}}',
        )
        for body in bodies:
            with self.subTest(body=body):
                provider = NitradoProvider(
                    self.config,
                    _Transport(NitradoHttpResponse(status=200, body=body)),
                )
                with self.assertRaises(NitradoMalformedResponseError):
                    provider.read_status(self._context())

    def test_maps_provider_failures_to_safe_typed_errors(self):
        cases = (
            (401, NitradoAuthenticationError),
            (403, NitradoInsufficientScopeError),
            (429, NitradoRateLimitedError),
            (503, NitradoUnavailableError),
        )
        for status, expected in cases:
            with self.subTest(status=status):
                provider = NitradoProvider(
                    self.config,
                    _Transport(NitradoHttpResponse(status=status, body=b"sensitive provider body")),
                )
                with self.assertRaises(expected) as raised:
                    provider.validate_credential(b"secret-token")
                self.assertNotIn("secret-token", repr(raised.exception))
                self.assertNotIn("sensitive provider body", repr(raised.exception))

    def test_rejects_malformed_contracts(self):
        bodies = (
            b"not-json",
            b'{"status":"success","data":{"services":{}}}',
            b'{"status":"success","data":{"services":[{"type":"gameserver"}]}}',
        )
        for body in bodies:
            with self.subTest(body=body):
                provider = NitradoProvider(
                    self.config,
                    _Transport(NitradoHttpResponse(status=200, body=body)),
                )
                with self.assertRaises(NitradoMalformedResponseError):
                    provider.validate_credential(b"token")

    def test_http_timeout_is_a_safe_unavailable_error(self):
        transport = NitradoHttpTransport()
        with patch("twe.services.nitrado_provider.urlopen", side_effect=socket.timeout):
            with self.assertRaises(NitradoUnavailableError) as raised:
                transport.get(
                    "https://api.nitrado.net/services",
                    {"Authorization": "Bearer secret-token"},
                    1.0,
                )
        self.assertNotIn("secret-token", repr(raised.exception))


if __name__ == "__main__":
    unittest.main()
