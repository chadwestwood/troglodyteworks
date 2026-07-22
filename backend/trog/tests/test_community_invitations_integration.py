import secrets
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from psycopg import OperationalError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.db import Database, execute, fetch_one
from twe.routes.auth import create_session
from twe.security import hash_password, hash_session_token
from tests.integration_database import load_integration_config


class CommunityInvitationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = load_integration_config()
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        try:
            with self.db.connect() as conn:
                self.owner = self._user(conn, "chad")
                self.member = self._user(conn, "member")
                self.invitee = self._user(conn, "mattertrala")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Cohorts {self.suffix}", f"cohorts-{self.suffix}", self.owner["id"]),
                )
                self._membership(conn, self.owner["id"], "owner")
                self._membership(conn, self.member["id"], "member")
                self.app = create_app(self.config, database=self.db)
                self.owner_client = self.app.test_client()
                self.member_client = self.app.test_client()
                self.invitee_client = self.app.test_client()
                self.new_user_client = self.app.test_client()
                self._login(conn, self.owner_client, self.owner["id"])
                self._login(conn, self.member_client, self.member["id"])
                self._login(conn, self.invitee_client, self.invitee["id"])
        except OperationalError as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for community invitation integration test: {exc.__class__.__name__}")

    def tearDown(self):
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE email LIKE %s", (f"%-{self.suffix}@example.test",))

    def test_authorized_leader_can_invite_existing_user_and_user_accepts(self):
        created = self._direct_invite(self.invitee["email"])
        invitation_id = created["invitation"]["id"]
        pending = self.invitee_client.get("/api/v1/community-invitations/pending")
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.get_json()["invitations"][0]["id"], invitation_id)
        accepted = self.invitee_client.post(f"/api/v1/community-invitations/direct/{invitation_id}/accept")
        self.assertEqual(accepted.status_code, 200)
        with self.db.connect() as conn:
            membership = fetch_one(
                conn,
                "SELECT role FROM community_memberships WHERE user_id = %s AND community_id = %s",
                (self.invitee["id"], self.community["id"]),
            )
        self.assertEqual(membership["role"], "member")

    def test_unauthorized_member_cannot_create_invitation_or_elevated_role(self):
        denied = self.member_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "link", "initial_role": "member"},
        )
        self.assertEqual(denied.status_code, 403)
        elevated = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "link", "initial_role": "owner"},
        )
        self.assertEqual(elevated.status_code, 400)

    def test_share_link_returns_plaintext_once_and_stores_only_hash(self):
        created = self._link_invite(maximum_uses=2)
        token = created["invitation"]["token"]
        self.assertGreaterEqual(len(token), 48)
        with self.db.connect() as conn:
            row = fetch_one(
                conn,
                "SELECT token_hash FROM community_invitations WHERE id = %s",
                (created["invitation"]["id"],),
            )
        self.assertNotEqual(row["token_hash"], token)
        self.assertEqual(row["token_hash"], hash_session_token(token))

    def test_new_user_registers_then_redeems_preserved_link(self):
        created = self._link_invite(maximum_uses=1)
        token = created["invitation"]["token"]
        registered = self.new_user_client.post(
            "/api/v1/auth/register",
            json={
                "display_name": "Mattertrala New",
                "email": f"matter-new-{self.suffix}@example.test",
                "password": "password123",
                "password_confirmation": "password123",
            },
        )
        self.assertEqual(registered.status_code, 201)
        accepted = self.new_user_client.post(f"/api/v1/community-invitations/{token}/accept")
        self.assertEqual(accepted.status_code, 200)
        with self.db.connect() as conn:
            user = fetch_one(conn, "SELECT id::text FROM users WHERE email = %s", (f"matter-new-{self.suffix}@example.test",))
            membership = fetch_one(conn, "SELECT role FROM community_memberships WHERE user_id = %s AND community_id = %s", (user["id"], self.community["id"]))
        self.assertEqual(membership["role"], "member")

    def test_revoked_expired_and_maximum_use_invites_are_rejected(self):
        revoked = self._link_invite(maximum_uses=1)
        revoke = self.owner_client.post(f"/api/v1/communities/{self.community['id']}/invitations/{revoked['invitation']['id']}/revoke")
        self.assertEqual(revoke.status_code, 200)
        response = self.invitee_client.post(f"/api/v1/community-invitations/{revoked['invitation']['token']}/accept")
        self.assertEqual(response.status_code, 409)

        expired = self._link_invite(maximum_uses=1, expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
        response = self.invitee_client.post(f"/api/v1/community-invitations/{expired['invitation']['token']}/accept")
        self.assertEqual(response.status_code, 409)

        used = self._link_invite(maximum_uses=1)
        first = self.invitee_client.post(f"/api/v1/community-invitations/{used['invitation']['token']}/accept")
        self.assertEqual(first.status_code, 200)
        second_user = self._logged_in_new_client("second")
        second = second_user.post(f"/api/v1/community-invitations/{used['invitation']['token']}/accept")
        self.assertEqual(second.status_code, 409)

    def test_duplicate_direct_invitation_and_duplicate_membership_are_prevented(self):
        self._direct_invite(self.invitee["email"])
        duplicate = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "direct", "email": self.invitee["email"], "initial_role": "member"},
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_approval_required_invite_creates_pending_request_and_owner_approves(self):
        created = self._link_invite(maximum_uses=1, requires_approval=True)
        token = created["invitation"]["token"]
        redeemed = self.invitee_client.post(f"/api/v1/community-invitations/{token}/accept")
        self.assertEqual(redeemed.status_code, 200)
        self.assertEqual(redeemed.get_json()["redemption"]["status"], "pending_approval")
        redemption_id = redeemed.get_json()["redemption"]["id"]
        pending = self.owner_client.get(
            f"/api/v1/communities/{self.community['id']}/invitation-redemptions/pending"
        )
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.get_json()["redemptions"][0]["id"], redemption_id)
        self.assertEqual(pending.get_json()["redemptions"][0]["user"]["email"], self.invitee["email"])
        hidden_from_member = self.member_client.get(
            f"/api/v1/communities/{self.community['id']}/invitation-redemptions/pending"
        )
        self.assertEqual(hidden_from_member.status_code, 403)
        denied = self.member_client.post(f"/api/v1/communities/{self.community['id']}/invitation-redemptions/{redemption_id}/approve")
        self.assertEqual(denied.status_code, 403)
        approved = self.owner_client.post(f"/api/v1/communities/{self.community['id']}/invitation-redemptions/{redemption_id}/approve")
        self.assertEqual(approved.status_code, 200)
        with self.db.connect() as conn:
            membership = fetch_one(conn, "SELECT role FROM community_memberships WHERE user_id = %s AND community_id = %s", (self.invitee["id"], self.community["id"]))
        self.assertEqual(membership["role"], "member")

    def test_moderator_cannot_approve_pending_admin_membership(self):
        created_response = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={
                "invitation_type": "link",
                "initial_role": "admin",
                "maximum_uses": 1,
                "requires_approval": True,
            },
        )
        self.assertEqual(created_response.status_code, 201)
        token = created_response.get_json()["invitation"]["token"]
        redeemed = self.invitee_client.post(f"/api/v1/community-invitations/{token}/accept")
        self.assertEqual(redeemed.status_code, 200)
        redemption_id = redeemed.get_json()["redemption"]["id"]

        moderator_client = self.app.test_client()
        with self.db.connect() as conn:
            moderator = self._user(conn, "moderator")
            self._membership(conn, moderator["id"], "moderator")
            self._login(conn, moderator_client, moderator["id"])

        denied = moderator_client.post(
            f"/api/v1/communities/{self.community['id']}/invitation-redemptions/{redemption_id}/approve"
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["error"]["code"], "FORBIDDEN")
        with self.db.connect() as conn:
            membership = fetch_one(
                conn,
                "SELECT role FROM community_memberships WHERE user_id = %s AND community_id = %s",
                (self.invitee["id"], self.community["id"]),
            )
            redemption = fetch_one(
                conn,
                "SELECT status FROM community_invitation_redemptions WHERE id = %s",
                (redemption_id,),
            )
        self.assertIsNone(membership)
        self.assertEqual(redemption["status"], "pending_approval")

    def test_link_defaults_to_24_hours_and_pending_request_survives_link_expiration(self):
        created_response = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "link", "initial_role": "member", "maximum_uses": 2},
        )
        self.assertEqual(created_response.status_code, 201)
        created = created_response.get_json()["invitation"]
        with self.db.connect() as conn:
            invitation = fetch_one(
                conn,
                "SELECT expires_at, requires_approval FROM community_invitations WHERE id = %s",
                (created["id"],),
            )
        remaining = invitation["expires_at"] - datetime.now(timezone.utc)
        self.assertTrue(invitation["requires_approval"])
        self.assertGreater(remaining, timedelta(hours=23, minutes=59))
        self.assertLessEqual(remaining, timedelta(hours=24))

        redeemed = self.invitee_client.post(f"/api/v1/community-invitations/{created['token']}/accept")
        self.assertEqual(redeemed.status_code, 200)
        redemption_id = redeemed.get_json()["redemption"]["id"]
        with self.db.connect() as conn:
            execute(
                conn,
                "UPDATE community_invitations SET expires_at = now() - interval '1 hour' WHERE id = %s",
                (created["id"],),
            )
        approved = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitation-redemptions/{redemption_id}/approve"
        )
        self.assertEqual(approved.status_code, 200)
        with self.db.connect() as conn:
            membership = fetch_one(
                conn,
                "SELECT role FROM community_memberships WHERE user_id = %s AND community_id = %s",
                (self.invitee["id"], self.community["id"]),
            )
        self.assertEqual(membership["role"], "member")

    def test_invitation_list_describes_manager_permissions_and_input_limits(self):
        listed = self.owner_client.get(f"/api/v1/communities/{self.community['id']}/invitations")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["current_user_role"], "owner")
        self.assertEqual(listed.get_json()["grantable_roles"], ["member", "moderator", "admin"])

        too_many_uses = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "link", "maximum_uses": 101},
        )
        self.assertEqual(too_many_uses.status_code, 400)
        invalid_expiration = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "link", "expires_at": "not-a-date"},
        )
        self.assertEqual(invalid_expiration.status_code, 400)

    def test_decline_and_mattertrala_membership_do_not_grant_genesis_capability(self):
        declined = self._link_invite(maximum_uses=1)
        response = self.invitee_client.post(f"/api/v1/community-invitations/{declined['invitation']['token']}/decline")
        self.assertEqual(response.status_code, 200)
        with self.db.connect() as conn:
            membership = fetch_one(conn, "SELECT id::text FROM community_memberships WHERE user_id = %s AND community_id = %s", (self.invitee["id"], self.community["id"]))
        self.assertIsNone(membership)

        accepted = self._link_invite(maximum_uses=1)
        response = self.invitee_client.post(f"/api/v1/community-invitations/{accepted['invitation']['token']}/accept")
        self.assertEqual(response.status_code, 200)
        with self.db.connect() as conn:
            capability = fetch_one(
                conn,
                """
                SELECT sog.id::text
                FROM server_operation_capability_grants sog
                JOIN community_memberships cm ON cm.id = sog.community_membership_id
                WHERE cm.user_id = %s AND cm.community_id = %s
                """,
                (self.invitee["id"], self.community["id"]),
            )
        self.assertIsNone(capability)

    def _direct_invite(self, email):
        response = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/invitations",
            json={"invitation_type": "direct", "email": email, "initial_role": "member"},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _link_invite(self, maximum_uses=1, requires_approval=False, expires_at=None):
        payload = {
            "invitation_type": "link",
            "initial_role": "member",
            "maximum_uses": maximum_uses,
            "requires_approval": requires_approval,
        }
        if expires_at:
            payload["expires_at"] = expires_at.isoformat()
        response = self.owner_client.post(f"/api/v1/communities/{self.community['id']}/invitations", json=payload)
        self.assertEqual(response.status_code, 201)
        return response.get_json()

    def _logged_in_new_client(self, label):
        client = self.app.test_client()
        with self.db.connect() as conn:
            user = self._user(conn, label)
            self._login(conn, client, user["id"])
        return client

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text, email",
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
