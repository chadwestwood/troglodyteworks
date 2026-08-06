import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.db import Database, execute, fetch_one
from twe.discord_bot.authorization import authorize, resolve_guild, resolve_identity
from twe.discord_bot.service import _finish_restart_operation
from twe.discord_bot.personality import personality_for_guild, update_guild_personality
from twe.security import hash_password
from tests.integration_database import load_integration_config


class DiscordFoundationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database(load_integration_config().database_url)
        try:
            with cls.db.connect() as conn:
                fetch_one(conn, "SELECT 1 FROM discord_guild_installations LIMIT 1")
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL or Discord migration unavailable: {exc.__class__.__name__}")

    def setUp(self):
        self.suffix = secrets.token_hex(8)
        self.guild_id = str(secrets.randbelow(8_000_000_000_000_000_000) + 1_000_000_000_000_000_000)
        self.owner_discord_id = str(int(self.guild_id) + 1)
        self.member_discord_id = str(int(self.guild_id) + 2)
        with self.db.connect() as conn:
            self.owner = self._user(conn, "owner")
            self.member = self._user(conn, "member")
            self.community = fetch_one(conn, "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text", (f"Discord {self.suffix}", f"discord-{self.suffix}", self.owner["id"]))
            self.server = fetch_one(conn, "INSERT INTO game_servers (community_id,name,slug,game_type,management_adapter) VALUES (%s,'Discord Server','discord-server','ARK Survival Ascended','local_asa') RETURNING id::text", (self.community["id"],))
            self.owner_membership = self._membership(conn, self.owner["id"], "owner")
            self.member_membership = self._membership(conn, self.member["id"], "member")
            self.installation = fetch_one(conn, "INSERT INTO discord_guild_installations (discord_guild_id,community_id,game_server_id,installed_by) VALUES (%s,%s,%s,%s) RETURNING id::text", (self.guild_id, self.community["id"], self.server["id"], self.owner["id"]))
            fetch_one(conn, "INSERT INTO discord_identities (discord_user_id,user_id,linked_at) VALUES (%s,%s,now()) RETURNING id", (self.owner_discord_id, self.owner["id"]))
            fetch_one(conn, "INSERT INTO discord_identities (discord_user_id,user_id,linked_at) VALUES (%s,%s,now()) RETURNING id", (self.member_discord_id, self.member["id"]))

    def tearDown(self):
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM audit_logs WHERE target_id = %s", (self.installation["id"],))
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s)", (self.owner["id"], self.member["id"]))

    def test_database_backed_guild_and_identity_resolution(self):
        with self.db.connect() as conn:
            context = resolve_guild(conn, self.guild_id)
            identity = resolve_identity(conn, self.owner_discord_id, self.community["id"])
        self.assertEqual(context.game_server_id, self.server["id"])
        self.assertEqual(identity.user_id, self.owner["id"])
        self.assertEqual(identity.role, "owner")

    def test_public_read_owner_restart_and_ordinary_member_denial(self):
        with self.db.connect() as conn:
            public = authorize(conn, self.guild_id, "333", "unlinked", "instance.status.read")
            owner = authorize(conn, self.guild_id, "333", self.owner_discord_id, "instance.restart.execute")
            member = authorize(conn, self.guild_id, "333", self.member_discord_id, "instance.restart.execute")
        self.assertTrue(public.allowed)
        self.assertTrue(owner.allowed)
        self.assertFalse(member.allowed)

    def test_personality_defaults_to_friendly_and_updates_with_an_audit(self):
        with self.db.connect() as conn:
            self.assertEqual(personality_for_guild(conn, self.guild_id), "friendly")
            update_guild_personality(
                conn,
                self.guild_id,
                "professional",
                self.owner_discord_id,
            )
            self.assertEqual(personality_for_guild(conn, self.guild_id), "professional")
            audit = fetch_one(
                conn,
                """
                SELECT user_id::text, details
                FROM audit_logs
                WHERE target_id = %s
                  AND action = 'discord.trog_personality.updated'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (self.installation["id"],),
            )
        self.assertEqual(audit["user_id"], self.owner["id"])
        self.assertEqual(audit["details"]["previous_preset"], "friendly")
        self.assertEqual(audit["details"]["new_preset"], "professional")

    def test_ordinary_member_with_server_capability_grant_is_authorized(self):
        with self.db.connect() as conn:
            fetch_one(
                conn,
                """
                INSERT INTO server_operation_capability_grants
                    (community_membership_id, capability, game_server_id, granted_by)
                VALUES (%s, 'instance.restart.execute', %s, %s)
                RETURNING id
                """,
                (self.member_membership["id"], self.server["id"], self.owner["id"]),
            )
            decision = authorize(
                conn, self.guild_id, "333", self.member_discord_id,
                "instance.restart.execute",
            )
        self.assertTrue(decision.allowed)

    def test_revoked_member_capability_grant_is_denied(self):
        with self.db.connect() as conn:
            grant = fetch_one(
                conn,
                """
                INSERT INTO server_operation_capability_grants
                    (community_membership_id, capability, game_server_id, granted_by, revoked_at)
                VALUES (%s, 'instance.restart.execute', %s, %s, now())
                RETURNING id
                """,
                (self.member_membership["id"], self.server["id"], self.owner["id"]),
            )
            self.assertIsNotNone(grant)
            decision = authorize(
                conn, self.guild_id, "333", self.member_discord_id,
                "instance.restart.execute",
            )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "capability_not_granted")

    def test_channel_policy_disables_read_capabilities(self):
        with self.db.connect() as conn:
            installation = resolve_guild(conn, self.guild_id)
            fetch_one(conn, "INSERT INTO discord_channel_policies (discord_guild_installation_id,discord_channel_id,capability_category,enabled) VALUES (%s,'333','read',false) RETURNING id", (installation.installation_id,))
            decision = authorize(conn, self.guild_id, "333", self.member_discord_id, "instance.status.read")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "channel_disabled")

    def test_restart_readiness_completes_the_original_operation_once(self):
        with self.db.connect() as conn:
            operation_id = self._restart_operation(conn)

        updated = _finish_restart_operation(
            self.db,
            operation_id,
            ready=True,
            message="Discord Server is ready for players.",
        )
        repeated = _finish_restart_operation(
            self.db,
            operation_id,
            ready=True,
            message="Discord Server is ready for players.",
        )

        with self.db.connect() as conn:
            state = fetch_one(
                conn,
                """
                SELECT so.status, so.current_stage, so.completed_at IS NOT NULL AS completed,
                       soc.status AS check_status,
                       (SELECT count(*)::int FROM audit_logs al
                        WHERE al.target_id = so.id
                          AND al.action = 'discord.server_operation.completed') AS audits
                FROM server_operations so
                JOIN server_operation_checks soc ON soc.server_operation_id = so.id
                WHERE so.id = %s AND soc.name = 'restart_readiness'
                """,
                (operation_id,),
            )
        self.assertTrue(updated)
        self.assertFalse(repeated)
        self.assertEqual(state["status"], "completed")
        self.assertEqual(state["current_stage"], "ready")
        self.assertTrue(state["completed"])
        self.assertEqual(state["check_status"], "passed")
        self.assertEqual(state["audits"], 1)

    def test_restart_readiness_timeout_fails_the_original_operation(self):
        with self.db.connect() as conn:
            operation_id = self._restart_operation(conn)

        updated = _finish_restart_operation(
            self.db,
            operation_id,
            ready=False,
            message="Discord Server did not become ready before the verification timeout.",
        )

        with self.db.connect() as conn:
            state = fetch_one(
                conn,
                """
                SELECT so.status, so.current_stage, so.completed_at IS NOT NULL AS completed,
                       soc.status AS check_status,
                       (SELECT count(*)::int FROM audit_logs al
                        WHERE al.target_id = so.id
                          AND al.action = 'discord.server_operation.failed') AS audits
                FROM server_operations so
                JOIN server_operation_checks soc ON soc.server_operation_id = so.id
                WHERE so.id = %s AND soc.name = 'restart_readiness'
                """,
                (operation_id,),
            )
        self.assertTrue(updated)
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["current_stage"], "readiness_timeout")
        self.assertTrue(state["completed"])
        self.assertEqual(state["check_status"], "failed")
        self.assertEqual(state["audits"], 1)

    def _user(self, conn, label):
        return fetch_one(conn, "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text", (f"{label}-{self.suffix}@example.test", hash_password("password123"), label))

    def _membership(self, conn, user_id, role):
        return fetch_one(conn, "INSERT INTO community_memberships (user_id,community_id,role) VALUES (%s,%s,%s) RETURNING id::text", (user_id, self.community["id"], role))

    def _restart_operation(self, conn):
        instance = fetch_one(
            conn,
            """
            INSERT INTO game_instances
                (game_server_id, name, slug, instance_type, game_identifier)
            VALUES (%s, 'Discord Server', %s, 'ark_map', 'Genesis_WP')
            RETURNING id::text
            """,
            (self.server["id"], f"restart-{secrets.token_hex(4)}"),
        )
        operation = fetch_one(
            conn,
            """
            INSERT INTO server_operations
                (game_instance_id, requested_by, capability, status, current_stage, started_at)
            VALUES (%s, %s, 'instance.restart.execute', 'verifying', 'readiness_check', now())
            RETURNING id::text
            """,
            (instance["id"], self.owner["id"]),
        )
        execute(
            conn,
            """
            INSERT INTO server_operation_checks
                (server_operation_id, name, status, started_at, result_message, sort_order)
            VALUES (%s, 'restart_readiness', 'running', now(), 'Waiting for readiness.', 1)
            """,
            (operation["id"],),
        )
        return operation["id"]


if __name__ == "__main__":
    unittest.main()
