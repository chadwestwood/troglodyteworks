import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.backfill_genesis_provider import GenesisBackfillError, backfill_genesis_provider
from twe.config import load_config
from twe.db import Database, execute, fetch_all, fetch_one
from twe.services.provider_resolution import resolve_game_server_provider


class ProviderFoundationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database(load_config().database_url)
        try:
            with cls.db.connect() as conn:
                present = fetch_one(conn, "SELECT to_regclass('provider_connections') IS NOT NULL AS present")
                if not present["present"]:
                    raise unittest.SkipTest("Provider foundation migration is not applied.")
        except unittest.SkipTest:
            raise
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable: {exc.__class__.__name__}: {exc}")

    def test_genesis_backfill_is_idempotent_and_preserves_relationships(self):
        with self.db.connect() as conn:
            before = self._genesis_snapshot(conn)
            first = backfill_genesis_provider(conn)
            second = backfill_genesis_provider(conn)
            after = self._genesis_snapshot(conn)
            conn.rollback()

        self.assertEqual(first["community_id"], second["community_id"])
        self.assertEqual(first["game_server_id"], second["game_server_id"])
        self.assertEqual(first["game_instance_id"], second["game_instance_id"])
        self.assertEqual(first["provider_connection_id"], second["provider_connection_id"])
        self.assertEqual(first["provider_resource_id"], second["provider_resource_id"])
        self.assertEqual(first["already_bound"], before["provider_resource_id"] is not None)
        self.assertTrue(second["already_bound"])
        self.assertEqual(before["community_id"], after["community_id"])
        self.assertEqual(before["game_server_id"], after["game_server_id"])
        self.assertEqual(before["game_instance_id"], after["game_instance_id"])
        self.assertEqual(before["operation_ids"], after["operation_ids"])
        self.assertEqual(before["discord_grant_ids"], after["discord_grant_ids"])
        self.assertEqual(before["capability_grant_ids"], after["capability_grant_ids"])
        self.assertEqual(after["backfill_audit_count"], 1)

    def test_provider_migration_applies_to_an_empty_foundation_schema(self):
        schema_name = f"provider_foundation_{secrets.token_hex(6)}"
        with self.db.connect() as conn:
            execute(conn, f'CREATE SCHEMA "{schema_name}"')
            execute(conn, f'SET LOCAL search_path TO "{schema_name}", public')
            for name in ("0001_initial_twe.sql", "0011_provider_foundation.sql"):
                conn.execute((ROOT / "migrations" / name).read_text())
            tables = {
                row["table_name"]
                for row in fetch_all(
                    conn,
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    """,
                    (schema_name,),
                )
            }
            conn.rollback()

        self.assertTrue(
            {
                "provider_connections",
                "provider_connection_secrets",
                "provider_oauth_states",
                "provider_resources",
                "game_servers",
            }.issubset(tables)
        )

    def test_missing_genesis_topology_fails_before_writes(self):
        with self.db.connect() as conn:
            before_count = fetch_one(
                conn,
                "SELECT count(*)::int AS count FROM provider_connections WHERE external_account_id = 'cohorts-local-asa'",
            )
            execute(
                conn,
                "UPDATE communities SET slug = 'cohorts-in-the-wild-hidden' WHERE slug = 'cohorts-in-the-wild'",
            )
            with self.assertRaisesRegex(GenesisBackfillError, r"found 0 \(missing\)"):
                backfill_genesis_provider(conn)
            count = fetch_one(
                conn,
                "SELECT count(*)::int AS count FROM provider_connections WHERE external_account_id = 'cohorts-local-asa'",
            )
            conn.rollback()
        self.assertEqual(count["count"], before_count["count"])

    def test_ambiguous_genesis_topology_fails_before_writes(self):
        suffix = secrets.token_hex(6)
        with self.db.connect() as conn:
            before_count = fetch_one(
                conn,
                "SELECT count(*)::int AS count FROM provider_connections WHERE external_account_id = 'cohorts-local-asa'",
            )
            community = fetch_one(
                conn,
                "SELECT id::text FROM communities WHERE slug = 'cohorts-in-the-wild'",
            )
            server = fetch_one(
                conn,
                """
                INSERT INTO game_servers
                    (community_id, name, slug, game_type, management_adapter)
                VALUES (%s, 'Second ARK', %s, 'ARK Survival Ascended', 'local_asa')
                RETURNING id::text
                """,
                (community["id"], f"second-ark-{suffix}"),
            )
            fetch_one(
                conn,
                """
                INSERT INTO game_instances
                    (game_server_id, name, slug, instance_type, game_identifier)
                VALUES (%s, 'Genesis', %s, 'map', 'Genesis_WP')
                RETURNING id::text
                """,
                (server["id"], f"genesis-{suffix}"),
            )
            with self.assertRaisesRegex(GenesisBackfillError, r"found 2 \(ambiguous\)"):
                backfill_genesis_provider(conn)
            count = fetch_one(
                conn,
                "SELECT count(*)::int AS count FROM provider_connections WHERE external_account_id = 'cohorts-local-asa'",
            )
            conn.rollback()
        self.assertEqual(count["count"], before_count["count"])

    def test_dual_resolver_selects_legacy_then_provider_path(self):
        suffix = secrets.token_hex(6)
        with self.db.connect() as conn:
            community = self._community(conn, suffix)
            server = self._server(conn, community["id"], suffix)
            legacy = resolve_game_server_provider(conn, server["id"], correlation_id="legacy-correlation")
            connection = self._connection(conn, community["id"], suffix)
            resource = self._resource(conn, connection["id"], suffix)
            execute(
                conn,
                "UPDATE game_servers SET provider_resource_id = %s WHERE id = %s",
                (resource["id"], server["id"]),
            )
            provider = resolve_game_server_provider(conn, server["id"], correlation_id="provider-correlation")
            conn.rollback()

        self.assertEqual(legacy.mode, "legacy")
        self.assertEqual(legacy.management_adapter, "local_asa")
        self.assertIsNone(legacy.context)
        self.assertEqual(provider.mode, "provider")
        self.assertEqual(provider.context.connection.provider_key, "self_hosted")
        self.assertEqual(provider.context.resource.id, resource["id"])
        self.assertEqual(provider.context.correlation_id, "provider-correlation")

    def test_cross_community_binding_is_rejected(self):
        suffix = secrets.token_hex(6)
        with self.db.connect() as conn:
            first = self._community(conn, f"first-{suffix}")
            second = self._community(conn, f"second-{suffix}")
            connection = self._connection(conn, first["id"], suffix)
            resource = self._resource(conn, connection["id"], suffix)
            server = self._server(conn, second["id"], suffix)
            with self.assertRaisesRegex(Exception, "different Community"):
                with conn.transaction():
                    execute(
                        conn,
                        "UPDATE game_servers SET provider_resource_id = %s WHERE id = %s",
                        (resource["id"], server["id"]),
                    )
            conn.rollback()

    def test_duplicate_discovery_and_binding_are_rejected(self):
        suffix = secrets.token_hex(6)
        with self.db.connect() as conn:
            community = self._community(conn, suffix)
            connection = self._connection(conn, community["id"], suffix)
            resource = self._resource(conn, connection["id"], suffix)
            with self.assertRaises(Exception):
                with conn.transaction():
                    self._resource(conn, connection["id"], suffix)
            first_server = self._server(conn, community["id"], f"first-{suffix}")
            second_server = self._server(conn, community["id"], f"second-{suffix}")
            execute(
                conn,
                "UPDATE game_servers SET provider_resource_id = %s WHERE id = %s",
                (resource["id"], first_server["id"]),
            )
            with self.assertRaises(Exception):
                with conn.transaction():
                    execute(
                        conn,
                        "UPDATE game_servers SET provider_resource_id = %s WHERE id = %s",
                        (resource["id"], second_server["id"]),
                    )
            conn.rollback()

    def _genesis_snapshot(self, conn):
        topology = fetch_one(
            conn,
            """
            SELECT c.id::text AS community_id,
                   gs.id::text AS game_server_id,
                   gs.provider_resource_id::text,
                   gi.id::text AS game_instance_id
            FROM communities c
            JOIN game_servers gs ON gs.community_id = c.id
            JOIN game_instances gi ON gi.game_server_id = gs.id
            WHERE c.slug = 'cohorts-in-the-wild'
              AND gs.slug = 'ark-survival-ascended'
              AND gi.slug = 'genesis'
            """,
        )
        if not topology:
            self.fail("The representative database does not contain the expected Genesis topology.")
        topology["operation_ids"] = tuple(
            row["id"]
            for row in fetch_all(
                conn,
                "SELECT id::text FROM server_operations WHERE game_instance_id = %s ORDER BY id",
                (topology["game_instance_id"],),
            )
        )
        topology["discord_grant_ids"] = tuple(
            row["id"]
            for row in fetch_all(
                conn,
                "SELECT id::text FROM discord_instance_access_grants WHERE game_instance_id = %s ORDER BY id",
                (topology["game_instance_id"],),
            )
        )
        topology["capability_grant_ids"] = tuple(
            row["id"]
            for row in fetch_all(
                conn,
                "SELECT id::text FROM server_operation_capability_grants WHERE game_instance_id = %s ORDER BY id",
                (topology["game_instance_id"],),
            )
        )
        topology["backfill_audit_count"] = fetch_one(
            conn,
            """
            SELECT count(*)::int AS count
            FROM audit_logs
            WHERE action = 'provider.foundation.genesis_backfilled'
              AND target_type = 'provider_resource'
              AND target_id = %s
            """,
            (topology["provider_resource_id"],),
        )["count"] if topology["provider_resource_id"] else 0
        return topology

    def _community(self, conn, suffix):
        return fetch_one(
            conn,
            "INSERT INTO communities (name, slug) VALUES (%s, %s) RETURNING id::text",
            (f"Provider {suffix}", f"provider-{suffix}"),
        )

    def _connection(self, conn, community_id, suffix):
        return fetch_one(
            conn,
            """
            INSERT INTO provider_connections
                (community_id, provider_key, display_name, auth_strategy, external_account_id, status)
            VALUES (%s, 'self_hosted', 'Test self-hosted', 'configuration', %s, 'active')
            RETURNING id::text
            """,
            (community_id, f"account-{suffix}"),
        )

    def _resource(self, conn, connection_id, suffix):
        return fetch_one(
            conn,
            """
            INSERT INTO provider_resources
                (provider_connection_id, resource_type, external_resource_id, display_name)
            VALUES (%s, 'game_server_service', %s, 'Test resource')
            RETURNING id::text
            """,
            (connection_id, f"resource-{suffix}"),
        )

    def _server(self, conn, community_id, suffix):
        return fetch_one(
            conn,
            """
            INSERT INTO game_servers
                (community_id, name, slug, game_type, management_adapter)
            VALUES (%s, 'Test ARK', %s, 'ARK Survival Ascended', 'local_asa')
            RETURNING id::text
            """,
            (community_id, f"ark-{suffix}"),
        )


if __name__ == "__main__":
    unittest.main()
