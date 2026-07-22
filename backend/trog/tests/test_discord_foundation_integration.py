import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.db import Database, execute, fetch_one
from twe.discord_bot.authorization import authorize, resolve_guild, resolve_identity
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
            fetch_one(conn, "INSERT INTO discord_guild_installations (discord_guild_id,community_id,game_server_id,installed_by) VALUES (%s,%s,%s,%s) RETURNING id", (self.guild_id, self.community["id"], self.server["id"], self.owner["id"]))
            fetch_one(conn, "INSERT INTO discord_identities (discord_user_id,user_id,linked_at) VALUES (%s,%s,now()) RETURNING id", (self.owner_discord_id, self.owner["id"]))
            fetch_one(conn, "INSERT INTO discord_identities (discord_user_id,user_id,linked_at) VALUES (%s,%s,now()) RETURNING id", (self.member_discord_id, self.member["id"]))

    def tearDown(self):
        with self.db.connect() as conn:
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

    def _user(self, conn, label):
        return fetch_one(conn, "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text", (f"{label}-{self.suffix}@example.test", hash_password("password123"), label))

    def _membership(self, conn, user_id, role):
        return fetch_one(conn, "INSERT INTO community_memberships (user_id,community_id,role) VALUES (%s,%s,%s) RETURNING id::text", (user_id, self.community["id"], role))


if __name__ == "__main__":
    unittest.main()
