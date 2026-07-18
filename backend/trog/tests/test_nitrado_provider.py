import json
import socket
import sys
import unittest
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
    NitradoUnavailableError,
)


class _Transport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, headers, timeout_seconds):
        self.calls.append((url, headers, timeout_seconds))
        if self.error:
            raise self.error
        return self.response


def _response(services):
    return NitradoHttpResponse(
        status=200,
        body=json.dumps({"status": "success", "data": {"services": services}}).encode(),
    )


class NitradoProviderTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")

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
