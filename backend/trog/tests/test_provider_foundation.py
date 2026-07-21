import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.services import local_asa
from twe.services.nitrado_provider import NitradoProvider
from twe.services.provider_contracts import (
    BoundSecretAccessor,
    ProviderConnectionRecord,
    ProviderContext,
    ProviderResourceRecord,
    ProviderSecretEnvelope,
    TimeoutPolicy,
)
from twe.services.provider_registry import (
    ProviderCapabilityUnavailable,
    build_provider_registry,
)
from twe.services.provider_resolution import ResolvedGameServerProvider, read_game_server_health
from twe.services.self_hosted_provider import SelfHostedProvider


class ProviderFoundationTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")
        self.context = ProviderContext(
            connection=ProviderConnectionRecord(
                id="connection-id",
                community_id="community-id",
                provider_key="self_hosted",
                display_name="Self-hosted",
                auth_strategy="configuration",
                external_account_id="local-installation",
                status="active",
            ),
            resource=ProviderResourceRecord(
                id="resource-id",
                provider_connection_id="connection-id",
                resource_type="game_server_service",
                external_resource_id="local-server",
                display_name="Genesis host",
                provider_game_key="ark_survival_ascended",
                normalized_status="unknown",
                provider_status="unknown",
            ),
            secret_accessor=BoundSecretAccessor(),
            correlation_id="correlation-id",
            timeout_policy=TimeoutPolicy(),
        )

    def test_self_hosted_status_is_lossless_local_asa_health(self):
        expected = {
            "overall_status": "degraded",
            "checked_at": "2026-07-17T12:00:00Z",
            "checks": [
                {"name": "process_running", "status": "passed", "message": "ok"},
                {"name": "broadcasting", "status": "failed", "message": "not ready"},
            ],
        }
        original_health = local_asa.health
        try:
            local_asa.health = lambda _config: expected
            status = SelfHostedProvider(self.config).read_status(self.context)
        finally:
            local_asa.health = original_health

        self.assertEqual(status.normalized_status, "degraded")
        self.assertEqual(status.as_health_payload(), expected)

    def test_legacy_and_provider_resolver_paths_return_equivalent_health(self):
        expected = {
            "overall_status": "ready",
            "checked_at": "2026-07-17T12:00:00Z",
            "checks": [
                {"name": "process_running", "status": "passed", "message": "ok"},
            ],
        }
        legacy = ResolvedGameServerProvider(mode="legacy", management_adapter="local_asa")
        provider = ResolvedGameServerProvider(
            mode="provider",
            management_adapter="local_asa",
            context=self.context,
        )
        original_health = local_asa.health
        try:
            local_asa.health = lambda _config: expected
            legacy_health = read_game_server_health(legacy, self.config)
            provider_health = read_game_server_health(provider, self.config)
        finally:
            local_asa.health = original_health

        self.assertEqual(legacy_health, expected)
        self.assertEqual(provider_health, expected)

    def test_registry_exposes_only_registered_capabilities(self):
        registry = build_provider_registry(self.config)
        self.assertEqual(
            registry.connection_describer("self_hosted").describe_connection().provider_key,
            "self_hosted",
        )
        self.assertIsInstance(registry.status_reader("self_hosted"), SelfHostedProvider)
        with self.assertRaises(ProviderCapabilityUnavailable):
            registry.resource_discoverer("self_hosted")
        with self.assertRaises(ProviderCapabilityUnavailable):
            registry.status_reader("pterodactyl")
        self.assertEqual(
            registry.connection_describer("nitrado").describe_connection().provider_key,
            "nitrado",
        )
        self.assertIsNotNone(registry.credential_validator("nitrado"))
        self.assertIsNotNone(registry.credential_resource_discoverer("nitrado"))
        self.assertIsInstance(registry.status_reader("nitrado"), NitradoProvider)

    def test_secret_envelope_and_context_repr_redact_secret_material(self):
        secret = ProviderSecretEnvelope(
            storage_kind="encrypted_payload",
            encrypted_payload=b"sensitive-ciphertext",
            encryption_nonce=b"sensitive-nonce",
            key_version="key-1",
        )
        context = ProviderContext(
            connection=self.context.connection,
            resource=self.context.resource,
            secret_accessor=BoundSecretAccessor(secret),
            correlation_id="correlation-id",
            timeout_policy=TimeoutPolicy(),
        )
        rendered = repr(context)
        self.assertNotIn("sensitive-ciphertext", rendered)
        self.assertNotIn("sensitive-nonce", rendered)
        self.assertNotIn("key-1", rendered)
        self.assertIs(context.secret_accessor.read_envelope(), secret)


if __name__ == "__main__":
    unittest.main()
