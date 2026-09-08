import secrets
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.integration_database import load_integration_config
from twe.app import create_app
from twe.db import Database, execute, fetch_one
from twe.discord_bot.core import respond_to_request
from twe.routes.auth import create_session
from twe.security import hash_password


class PlayerWorldConnectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_integration_config()
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        try:
            with self.db.connect() as conn:
                fetch_one(conn, "SELECT 1 FROM player_world_connections LIMIT 1")
                self.user = fetch_one(
                    conn,
                    """
                    INSERT INTO users (email, password_hash, display_name)
                    VALUES (%s, %s, 'Minecraft Player')
                    RETURNING id::text
                    """,
                    (f"minecraft-{self.suffix}@example.test", hash_password("password123")),
                )
                self.community = fetch_one(
                    conn,
                    """
                    INSERT INTO communities (name, slug, created_by)
                    VALUES (%s, %s, %s)
                    RETURNING id::text
                    """,
                    (f"Minecraft {self.suffix}", f"minecraft-{self.suffix}", self.user["id"]),
                )
                execute(
                    conn,
                    "INSERT INTO community_memberships (user_id, community_id, role) VALUES (%s, %s, 'member')",
                    (self.user["id"], self.community["id"]),
                )
                self.app = create_app(self.config, database=self.db)
                self.client = self.app.test_client()
                token = create_session(conn, self.user["id"], self.config)
                self.client.set_cookie(self.config.session_cookie_name, token)
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL or player-world migration unavailable: {exc.__class__.__name__}")

    def tearDown(self):
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id = %s", (self.user["id"],))

    def test_member_creates_pairs_reports_and_revokes_own_connection(self):
        missing_csrf = self.client.post(
            f"/api/v1/communities/{self.community['id']}/player-world-connections",
            json={"display_name": "Should not be created"},
        )
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(missing_csrf.get_json()["error"]["code"], "CSRF_REJECTED")

        created = self.client.post(
            f"/api/v1/communities/{self.community['id']}/player-world-connections",
            json={"display_name": "The Minecraft world I play on"},
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(created.status_code, 201)
        connection = created.get_json()["player_world_connection"]
        self.assertEqual(connection["status"], "unpaired")
        self.assertFalse(connection["discord_sharing_enabled"])
        pairing_token = connection["pairing"]["token"]

        paired = self.app.test_client().post(
            "/api/v1/minecraft-client/pair",
            json={
                "pairing_token": pairing_token,
                "device_name": "Chad's PC",
                "minecraft_version": "26.2",
                "mod_version": "0.1.0",
            },
        )
        self.assertEqual(paired.status_code, 201)
        device_token = paired.get_json()["device"]["token"]
        reused = self.app.test_client().post(
            "/api/v1/minecraft-client/pair",
            json={
                "pairing_token": pairing_token,
                "device_name": "Other PC",
                "minecraft_version": "26.2",
                "mod_version": "0.1.0",
            },
        )
        self.assertEqual(reused.status_code, 401)

        event_id = str(uuid4())
        event = {
            "event_id": event_id,
            "event_type": "world.joined",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "world_label": "Friends",
                "server_fingerprint": "b" * 64,
                "connection_kind": "multiplayer",
            },
        }
        headers = {"Authorization": f"Bearer {device_token}"}
        ingested = self.app.test_client().post(
            "/api/v1/minecraft-client/events", json={"events": [event]}, headers=headers
        )
        duplicate = self.app.test_client().post(
            "/api/v1/minecraft-client/events", json={"events": [event]}, headers=headers
        )
        self.assertEqual(ingested.status_code, 200)
        self.assertEqual(ingested.get_json()["status"], "in_world")
        self.assertEqual(duplicate.get_json()["duplicates"], 1)

        delayed_leave = {
            "event_id": str(uuid4()),
            "event_type": "world.left",
            "occurred_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
            "payload": {},
        }
        delayed = self.app.test_client().post(
            "/api/v1/minecraft-client/events",
            json={"events": [delayed_leave]},
            headers=headers,
        )
        self.assertEqual(delayed.status_code, 200)
        self.assertEqual(delayed.get_json()["status"], "in_world")

        discord_guild_id = str(secrets.randbelow(800_000_000_000_000_000) + 100_000_000_000_000_000)
        with self.db.connect() as conn:
            game_server = fetch_one(
                conn,
                """
                INSERT INTO game_servers
                    (community_id, name, slug, game_type, management_adapter)
                VALUES (%s, 'Existing ARK service', %s, 'ARK: Survival Ascended', 'local_asa')
                RETURNING id::text
                """,
                (self.community["id"], f"existing-ark-{self.suffix}"),
            )
            execute(
                conn,
                """
                INSERT INTO discord_guild_installations
                    (discord_guild_id, community_id, game_server_id, installed_by)
                VALUES (%s, %s, %s, %s)
                """,
                (discord_guild_id, self.community["id"], game_server["id"], self.user["id"]),
            )
            execute(
                conn,
                """
                INSERT INTO discord_guild_authority_verifications
                    (user_id, discord_user_id, discord_guild_id, discord_guild_name,
                     can_manage_guild, authority_source, expires_at)
                VALUES (%s, %s, %s, 'Cohorts in the Wild', true, 'administrator', %s)
                """,
                (self.user["id"], discord_guild_id, discord_guild_id, datetime.now(timezone.utc) + timedelta(hours=1)),
            )

        guilds = self.client.get(f"/api/v1/player-world-connections/{connection['id']}/discord-bindings")
        self.assertEqual(guilds.status_code, 200)
        self.assertTrue(guilds.get_json()["discord_guilds"][0]["trog_installed_for_community"])
        bound = self.client.post(
            f"/api/v1/player-world-connections/{connection['id']}/discord-bindings",
            json={"discord_guild_id": discord_guild_id},
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(bound.status_code, 201)
        with self.db.connect() as conn:
            reply = respond_to_request(
                "player_world_presence", discord_guild_id, "999", discord_guild_id,
                conn, self.config,
            )
        self.assertEqual(reply.code, "player_world_presence")
        self.assertIn("currently playing", reply.text)
        self.assertIn("not by the Minecraft server", reply.text)

        revoked = self.client.delete(
            f"/api/v1/player-world-connections/{connection['id']}",
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(revoked.status_code, 200)
        rejected = self.app.test_client().post(
            "/api/v1/minecraft-client/events", json={"events": [event]}, headers=headers
        )
        self.assertEqual(rejected.status_code, 401)


if __name__ == "__main__":
    unittest.main()
