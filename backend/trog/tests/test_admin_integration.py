import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config
from twe.db import Database, execute, fetch_one
from twe.routes.auth import create_session
from twe.security import hash_password
from tests.integration_database import load_integration_config


class AdminIntegrationTests(unittest.TestCase):
    def setUp(self):
        loaded = load_integration_config()
        self.suffix = secrets.token_hex(8)
        self.admin_email = f"admin-{self.suffix}@example.test"
        self.member_email = f"member-{self.suffix}@example.test"
        self.config = Config(database_url=loaded.database_url, admin_emails=(self.admin_email,))
        self.db = Database(self.config.database_url)
        try:
            with self.db.connect() as conn:
                self.admin = self._user(conn, "admin", self.admin_email)
                self.member = self._user(conn, "member", self.member_email)
                self.real_user = self._user(conn, "real-person", f"real-{self.suffix}@sample.org")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Admin Review {self.suffix}", f"admin-review-{self.suffix}", self.admin["id"]),
                )
                fetch_one(
                    conn,
                    "INSERT INTO community_memberships (user_id, community_id, role) VALUES (%s,%s,'owner') RETURNING id",
                    (self.admin["id"], self.community["id"]),
                )
                self.server = fetch_one(
                    conn,
                    "INSERT INTO game_servers (community_id,name,slug,game_type,management_adapter,status) VALUES (%s,'Admin ARK','admin-ark','ARK','local_asa','online') RETURNING id::text",
                    (self.community["id"],),
                )
                self.instance = fetch_one(
                    conn,
                    "INSERT INTO game_instances (game_server_id,name,slug,instance_type,game_identifier,status) VALUES (%s,'Admin Genesis','admin-genesis','ark_map','Genesis_WP','online') RETURNING id::text",
                    (self.server["id"],),
                )
                fetch_one(
                    conn,
                    """
                    INSERT INTO discord_instance_access_grants
                        (provider_community_id,game_server_id,game_instance_id,requested_by)
                    VALUES (%s,%s,%s,%s)
                    RETURNING id::text
                    """,
                    (self.community["id"], self.server["id"], self.instance["id"], self.admin["id"]),
                )
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for admin integration test: {exc.__class__.__name__}")
        self.app = create_app(self.config, database=self.db)
        self.admin_client = self.app.test_client()
        self.member_client = self.app.test_client()
        with self.db.connect() as conn:
            self._login(conn, self.admin_client, self.admin["id"])
            self._login(conn, self.member_client, self.member["id"])

    def tearDown(self):
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s,%s)", (self.admin["id"], self.member["id"], self.real_user["id"]))

    def test_admin_can_list_users_and_communities(self):
        users = self.admin_client.get("/api/v1/admin/users")
        communities = self.admin_client.get("/api/v1/admin/communities")
        overview = self.admin_client.get("/api/v1/admin/overview")
        discord_access = self.admin_client.get("/api/v1/admin/discord-access")

        self.assertEqual(users.status_code, 200)
        admin_user = next(user for user in users.get_json()["users"] if user["email"] == self.admin_email)
        self.assertTrue(admin_user["is_test"])
        self.assertEqual(admin_user["memberships"][0]["role"], "owner")
        self.assertFalse(next(user for user in users.get_json()["users"] if user["email"] == self.real_user["email"])["is_test"])
        self.assertEqual(communities.status_code, 200)
        community = next(community for community in communities.get_json()["communities"] if community["slug"] == f"admin-review-{self.suffix}")
        self.assertTrue(community["is_test"])
        self.assertEqual(community["game_server_count"], 1)
        self.assertEqual(community["instance_count"], 1)
        self.assertEqual(community["pending_trog_requests"], 1)
        self.assertEqual(overview.status_code, 200)
        self.assertGreaterEqual(overview.get_json()["overview"]["people"], 1)
        self.assertGreaterEqual(overview.get_json()["overview"]["test_accounts"], 2)
        self.assertEqual(discord_access.status_code, 200)
        self.assertTrue(any(request["instance_name"] == "Admin Genesis" for request in discord_access.get_json()["discord_access"]))

    def test_non_admin_is_rejected(self):
        response = self.member_client.get("/api/v1/admin/users")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"]["code"], "FORBIDDEN")
        self.assertEqual(self.member_client.get("/api/v1/admin/discord-access").status_code, 403)

    def test_admin_page_is_served(self):
        response = self.admin_client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"People, communities, and access", response.data)

    def _user(self, conn, label, email):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text, email",
            (email, hash_password("password123"), label),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)


if __name__ == "__main__":
    unittest.main()
