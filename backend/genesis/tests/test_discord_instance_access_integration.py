import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import load_config
from twe.db import Database, execute, fetch_one
from twe.discord_bot.authorization import authorize
from twe.routes.auth import create_session
from twe.security import hash_password


class DiscordInstanceAccessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        self.guild_id = str(secrets.randbelow(8_000_000_000_000_000_000) + 1_000_000_000_000_000_000)
        self.discord_user_id = str(int(self.guild_id) + 1)
        try:
            with self.db.connect() as conn:
                self.owner = self._user(conn, "cohorts-owner")
                self.matter = self._user(conn, "mattertrala")
                self.member = self._user(conn, "ordinary-member")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Cohorts {self.suffix}", f"cohorts-{self.suffix}", self.owner["id"]),
                )
                self.server = fetch_one(
                    conn,
                    """
                    INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter)
                    VALUES (%s, 'ARK Survival Ascended', 'ark-survival-ascended', 'ARK Survival Ascended', 'local_asa')
                    RETURNING id::text
                    """,
                    (self.community["id"],),
                )
                self.instance = fetch_one(
                    conn,
                    """
                    INSERT INTO game_instances (game_server_id, name, slug, instance_type, game_identifier, status)
                    VALUES (%s, 'Genesis', 'genesis', 'ark_map', 'Genesis_WP', 'online')
                    RETURNING id::text
                    """,
                    (self.server["id"],),
                )
                self._membership(conn, self.owner["id"], "owner")
                self._membership(conn, self.matter["id"], "member")
                self._membership(conn, self.member["id"], "member")
                self.app = create_app(self.config, database=self.db)
                self.owner_client = self.app.test_client()
                self.matter_client = self.app.test_client()
                self.member_client = self.app.test_client()
                self._login(conn, self.owner_client, self.owner["id"])
                self._login(conn, self.matter_client, self.matter["id"])
                self._login(conn, self.member_client, self.member["id"])
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for instance access integration test: {exc.__class__.__name__}")

    def tearDown(self):
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s,%s)", (self.owner["id"], self.matter["id"], self.member["id"]))

    def test_mattertrala_request_to_active_lizzlive_grant(self):
        grant_id = self._create_request(channel_scope="allowlist")

        verification = self._verify_discord(grant_id, self.discord_user_id, permissions=32)
        self.assertEqual(verification["request"]["status"], "pending_provider_approval")

        denied = self.member_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={"approved_capabilities": ["instance.status.read"]},
        )
        self.assertEqual(denied.status_code, 403)

        install = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/bot-installation",
            json={"allowed_channel_ids": ["333"]},
        )
        self.assertEqual(install.status_code, 200)
        self.assertEqual(install.get_json()["request"]["status"], "pending_provider_approval")

        approval = self.owner_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={
                "approved_capabilities": [
                    "instance.status.read",
                    "instance.players.count.read",
                    "instance.players.names.read",
                ],
                "channel_scope": "allowlist",
            },
        )
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(approval.get_json()["request"]["status"], "active")

        with self.db.connect() as conn:
            status = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
            count = authorize(conn, self.guild_id, "333", "public-user", "instance.players.count.read")
            names = authorize(conn, self.guild_id, "333", "public-user", "instance.players.names.read")
            wrong_channel = authorize(conn, self.guild_id, "444", "public-user", "instance.status.read")
            restart = authorize(conn, self.guild_id, "333", self.discord_user_id, "instance.restart.execute")
            lizzlive = fetch_one(conn, "SELECT id::text FROM communities WHERE slug = %s", (f"lizzlive-{self.suffix}",))

        self.assertTrue(status.allowed)
        self.assertIn("Cohorts", status.context.game_server_name)
        self.assertIn("Genesis", status.context.game_server_name)
        self.assertTrue(count.allowed)
        self.assertTrue(names.allowed)
        self.assertFalse(wrong_channel.allowed)
        self.assertEqual(wrong_channel.reason, "channel_disabled")
        self.assertFalse(restart.allowed)
        self.assertIn(restart.reason, {"channel_disabled", "capability_not_granted"})
        self.assertIsNone(lizzlive)

    def test_unlinked_discord_identity_cannot_complete_verification(self):
        grant_id = self._create_request()
        state = self._oauth_state(grant_id)
        response = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/discord-verification",
            json={
                "state": state,
                "discord_user_id": self.discord_user_id,
                "discord_guild_id": self.guild_id,
                "permissions": 32,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "DISCORD_IDENTITY_NOT_LINKED")

    def test_user_without_discord_guild_management_is_rejected(self):
        grant_id = self._create_request()
        self._link_identity(self.discord_user_id)
        state = self._oauth_state(grant_id)
        response = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/discord-verification",
            json={
                "state": state,
                "discord_user_id": self.discord_user_id,
                "discord_guild_id": self.guild_id,
                "permissions": 0,
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "DISCORD_GUILD_AUTHORITY_REQUIRED")

    def test_revoked_grant_stops_access(self):
        grant_id = self._active_grant()
        revoke = self.owner_client.post(f"/api/v1/discord/instance-access-grants/{grant_id}/revoke")
        self.assertEqual(revoke.status_code, 200)
        with self.db.connect() as conn:
            decision = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "guild_not_connected")

    def test_cross_community_instance_is_rejected(self):
        with self.db.connect() as conn:
            other_owner = self._user(conn, "other-owner")
            other_community = fetch_one(
                conn,
                "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                (f"Other {self.suffix}", f"other-{self.suffix}", other_owner["id"]),
            )
            other_server = fetch_one(
                conn,
                "INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter) VALUES (%s,'Other','other','ARK','local_asa') RETURNING id::text",
                (other_community["id"],),
            )
            other_instance = fetch_one(
                conn,
                "INSERT INTO game_instances (game_server_id, name, slug, instance_type, game_identifier) VALUES (%s,'Other Map','other-map','ark_map','Other') RETURNING id::text",
                (other_server["id"],),
            )
        response = self.matter_client.post(
            "/api/v1/discord/instance-access-requests",
            json={
                "provider_community_id": self.community["id"],
                "game_instance_id": other_instance["id"],
                "requested_capabilities": ["instance.status.read"],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "INSTANCE_NOT_FOUND")
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (other_community["id"],))
            execute(conn, "DELETE FROM users WHERE id = %s", (other_owner["id"],))

    def test_static_request_access_page_is_served(self):
        response = self.matter_client.get("/discord/request-access/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trog Discord Access", response.data)

    def _active_grant(self):
        grant_id = self._create_request()
        self._verify_discord(grant_id, self.discord_user_id, permissions=32)
        install = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/bot-installation",
            json={"allowed_channel_ids": ["333"]},
        )
        self.assertEqual(install.status_code, 200)
        approval = self.owner_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={"approved_capabilities": ["instance.status.read"]},
        )
        self.assertEqual(approval.status_code, 200)
        return grant_id

    def _create_request(self, channel_scope="all"):
        response = self.matter_client.post(
            "/api/v1/discord/instance-access-requests",
            json={
                "provider_community_id": self.community["id"],
                "game_instance_id": self.instance["id"],
                "requested_capabilities": [
                    "instance.status.read",
                    "instance.players.count.read",
                    "instance.players.names.read",
                ],
                "channel_scope": channel_scope,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["request"]["id"]

    def _verify_discord(self, grant_id, discord_user_id, permissions):
        self._link_identity(discord_user_id)
        state = self._oauth_state(grant_id)
        response = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/discord-verification",
            json={
                "state": state,
                "discord_user_id": discord_user_id,
                "discord_guild_id": self.guild_id,
                "discord_guild_name": "LizzLive",
                "permissions": permissions,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def _link_identity(self, discord_user_id):
        response = self.matter_client.post("/api/v1/discord/identity/link", json={"discord_user_id": discord_user_id})
        self.assertEqual(response.status_code, 200)

    def _oauth_state(self, grant_id):
        response = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/oauth-state",
            json={"purpose": "guild_verification"},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()["oauth"]["state"]

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text",
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), label),
        )

    def _membership(self, conn, user_id, role):
        return fetch_one(
            conn,
            "INSERT INTO community_memberships (user_id,community_id,role) VALUES (%s,%s,%s) RETURNING id::text",
            (user_id, self.community["id"], role),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)


if __name__ == "__main__":
    unittest.main()
