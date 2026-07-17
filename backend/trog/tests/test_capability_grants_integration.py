import secrets
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.assign_cohorts_owner import assign_owner
from twe.authorization import can_request_capability
from twe.config import load_config
from twe.db import Database, execute, fetch_one
from twe.security import hash_password


class CapabilityGrantIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database(load_config().database_url)
        try:
            with cls.db.connect() as conn:
                fetch_one(conn, "SELECT 1")
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable: {exc.__class__.__name__}")

    def setUp(self):
        self.suffix = secrets.token_hex(8)
        self.created_community_id = None
        with self.db.connect() as conn:
            self.owner = self._create_user(conn, "owner")
            self.admin = self._create_user(conn, "admin")
            self.member = self._create_user(conn, "member")
            self.community = fetch_one(
                conn,
                """
                INSERT INTO communities (name, slug, created_by)
                VALUES (%s, %s, %s)
                RETURNING id::text
                """,
                (f"Grant Test {self.suffix}", f"grant-test-{self.suffix}", self.owner["id"]),
            )
            self.created_community_id = self.community["id"]
            self.server = fetch_one(
                conn,
                """
                INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter)
                VALUES (%s, 'Grant Server', 'grant-server', 'ARK Survival Ascended', 'local_asa')
                RETURNING id::text
                """,
                (self.community["id"],),
            )
            self.other_server = fetch_one(
                conn,
                """
                INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter)
                VALUES (%s, 'Other Grant Server', 'other-grant-server', 'ARK Survival Ascended', 'local_asa')
                RETURNING id::text
                """,
                (self.community["id"],),
            )
            self.instance = self._create_instance(conn, self.server["id"], "grant-instance", 1)
            self.other_instance = self._create_instance(conn, self.server["id"], "other-instance", 2)
            self.other_server_instance = self._create_instance(conn, self.other_server["id"], "other-server-instance", 1)
            self.owner_membership = self._membership(conn, self.owner["id"], "owner")
            self.admin_membership = self._membership(conn, self.admin["id"], "admin")
            self.member_membership = self._membership(conn, self.member["id"], "member")

    def tearDown(self):
        if self.created_community_id:
            with self.db.connect() as conn:
                execute(conn, "DELETE FROM communities WHERE id = %s", (self.created_community_id,))
                execute(conn, "DELETE FROM users WHERE email LIKE %s", (f"%{self.suffix}@example.test",))

    def test_owner_and_grant_authorization(self):
        with self.db.connect() as conn:
            owner_access = self._access(self.owner_membership, self.server, self.instance, "owner")
            admin_access = self._access(self.admin_membership, self.server, self.instance, "admin")
            member_access = self._access(self.member_membership, self.server, self.instance, "member")

            self.assertTrue(can_request_capability(owner_access, "instance.status", conn))
            self.assertTrue(can_request_capability(owner_access, "instance.save", conn))
            self.assertFalse(can_request_capability(admin_access, "instance.status", conn))
            self.assertFalse(can_request_capability(member_access, "instance.status", conn))

            grant = self._grant(conn, self.member_membership["id"], "instance.status", game_instance_id=self.instance["id"])
            self.assertTrue(can_request_capability(member_access, "instance.status", conn))

            other_instance_access = self._access(self.member_membership, self.server, self.other_instance, "member")
            self.assertFalse(can_request_capability(other_instance_access, "instance.status", conn))

            execute(conn, "UPDATE server_operation_capability_grants SET revoked_at = now() WHERE id = %s", (grant["id"],))
            self.assertFalse(can_request_capability(member_access, "instance.status", conn))

            self._grant(conn, self.member_membership["id"], "instance.status", game_server_id=self.server["id"])
            self.assertTrue(can_request_capability(member_access, "instance.status", conn))
            self.assertTrue(can_request_capability(other_instance_access, "instance.status", conn))

            other_server_access = self._access(self.member_membership, self.other_server, self.other_server_instance, "member")
            self.assertFalse(can_request_capability(other_server_access, "instance.status", conn))

            self._grant(conn, self.admin_membership["id"], "instance.save")
            self.assertTrue(can_request_capability(admin_access, "instance.save", conn))
            self.assertFalse(can_request_capability(admin_access, "instance.restart", conn))

    def test_owner_assignment_is_idempotent(self):
        slug = f"assign-test-{self.suffix}"
        with self.db.connect() as conn:
            community = fetch_one(
                conn,
                """
                INSERT INTO communities (name, slug, created_by)
                VALUES (%s, %s, %s)
                RETURNING id::text, slug
                """,
                (f"Assign Test {self.suffix}", slug, self.owner["id"]),
            )
        try:
            first = assign_owner(self.db, self.member["email"].upper(), slug, self.owner["email"])
            second = assign_owner(self.db, self.member["email"], slug, self.owner["email"])
            self.assertEqual(first["membership_id"], second["membership_id"])
            with self.db.connect() as conn:
                row = fetch_one(
                    conn,
                    """
                    SELECT count(*)::int AS count, max(role) AS role
                    FROM community_memberships cm
                    JOIN users u ON u.id = cm.user_id
                    WHERE cm.community_id = %s AND lower(u.email) = %s
                    """,
                    (community["id"], self.member["email"]),
                )
                self.assertEqual(row["count"], 1)
                self.assertEqual(row["role"], "owner")
        finally:
            with self.db.connect() as conn:
                execute(conn, "DELETE FROM communities WHERE id = %s", (community["id"],))

    def _create_user(self, conn, label):
        return fetch_one(
            conn,
            """
            INSERT INTO users (email, password_hash, display_name)
            VALUES (%s, %s, %s)
            RETURNING id::text, email
            """,
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), f"{label}-{self.suffix}"),
        )

    def _create_instance(self, conn, server_id, slug, sort_order):
        return fetch_one(
            conn,
            """
            INSERT INTO game_instances (game_server_id, name, slug, instance_type, game_identifier, sort_order)
            VALUES (%s, %s, %s, 'map', %s, %s)
            RETURNING id::text
            """,
            (server_id, slug, slug, slug, sort_order),
        )

    def _membership(self, conn, user_id, role):
        return fetch_one(
            conn,
            """
            INSERT INTO community_memberships (user_id, community_id, role)
            VALUES (%s, %s, %s)
            RETURNING id::text, role
            """,
            (user_id, self.community["id"], role),
        )

    def _grant(self, conn, membership_id, capability, game_server_id=None, game_instance_id=None):
        return fetch_one(
            conn,
            """
            INSERT INTO server_operation_capability_grants
                (community_membership_id, capability, game_server_id, game_instance_id, granted_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id::text
            """,
            (membership_id, capability, game_server_id, game_instance_id, self.owner["id"]),
        )

    def _access(self, membership, server, instance, role):
        return {
            "membership_id": membership["id"],
            "role": role,
            "game_server_id": server["id"],
            "instance_id": instance["id"],
        }


if __name__ == "__main__":
    unittest.main()
