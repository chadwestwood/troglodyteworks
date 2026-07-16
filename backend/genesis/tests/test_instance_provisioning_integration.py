import secrets
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import load_config
from twe.db import Database, execute, fetch_one
from twe.routes.auth import create_session
from twe.security import hash_password
from twe.services import instance_provisioning
from twe.services.hosting import ProviderInstanceState


class _FakeProvider:
    def __init__(self, ready=True, fail_message=None):
        self._ready = ready
        self._fail_message = fail_message

    def create_instance(self, _spec):
        if self._fail_message:
            raise RuntimeError(self._fail_message)
        if self._ready:
            return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="ready")
        return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="provisioning")

    def get_instance_status(self, _provider_instance_id):
        if self._fail_message:
            return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="failed", detail=self._fail_message)
        return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="ready")

    def start_instance(self, _provider_instance_id):
        return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="ready")

    def stop_instance(self, _provider_instance_id):
        return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="ready")

    def restart_instance(self, _provider_instance_id):
        return ProviderInstanceState(provider_instance_id="ptero-123", provider_status="ready")


class InstanceProvisioningIntegrationTests(unittest.TestCase):
    def setUp(self):
        loaded = load_config()
        self.config = replace(loaded)
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        self.original_provider_for = instance_provisioning.provider_for
        instance_provisioning.provider_for = lambda _name, _config: _FakeProvider()
        try:
            with self.db.connect() as conn:
                self.owner = self._user(conn, "owner")
                self.member = self._user(conn, "member")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Provision Community {self.suffix}", f"provision-community-{self.suffix}", self.owner["id"]),
                )
                fetch_one(
                    conn,
                    "INSERT INTO community_memberships (user_id, community_id, role) VALUES (%s,%s,'owner') RETURNING id::text",
                    (self.owner["id"], self.community["id"]),
                )
                fetch_one(
                    conn,
                    "INSERT INTO community_memberships (user_id, community_id, role) VALUES (%s,%s,'member') RETURNING id::text",
                    (self.member["id"], self.community["id"]),
                )
                self.app = create_app(self.config, database=self.db)
                self.owner_client = self.app.test_client()
                self.member_client = self.app.test_client()
                self._login(conn, self.owner_client, self.owner["id"])
                self._login(conn, self.member_client, self.member["id"])
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for instance provisioning integration test: {exc.__class__.__name__}: {exc}")

    def tearDown(self):
        instance_provisioning.provider_for = self.original_provider_for
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s)", (self.owner["id"], self.member["id"]))

    def test_owner_can_provision_and_retry_idempotently(self):
        catalog = self.owner_client.get("/api/v1/game-catalog")
        self.assertEqual(catalog.status_code, 200)
        self.assertEqual(catalog.get_json()["games"][0]["key"], "ark_survival_ascended")

        payload = {
            "game_key": "ark_survival_ascended",
            "map_key": "the_island",
            "idempotency_key": f"req-{self.suffix}",
        }
        first = self.owner_client.post(f"/api/v1/communities/{self.community['id']}/instances", json=payload)
        self.assertEqual(first.status_code, 202)
        first_data = first.get_json()
        self.assertEqual(first_data["instance"]["status"], "online")
        self.assertEqual(first_data["instance"]["hosting_provider"], "pterodactyl")
        self.assertEqual(first_data["instance"]["provider_instance_id"], "ptero-123")

        retry = self.owner_client.post(f"/api/v1/communities/{self.community['id']}/instances", json=payload)
        self.assertEqual(retry.status_code, 200)
        retry_data = retry.get_json()
        self.assertEqual(retry_data["instance"]["id"], first_data["instance"]["id"])
        self.assertEqual(retry_data["server_operation"]["id"], first_data["server_operation"]["id"])

        operation = self.owner_client.get(f"/api/v1/server-operations/{first_data['server_operation']['id']}")
        self.assertEqual(operation.status_code, 200)
        self.assertEqual(operation.get_json()["server_operation"]["status"], "completed")

    def test_member_cannot_provision_and_invalid_selection_is_rejected(self):
        forbidden = self.member_client.post(
            f"/api/v1/communities/{self.community['id']}/instances",
            json={"game_key": "ark_survival_ascended", "map_key": "the_island"},
        )
        self.assertEqual(forbidden.status_code, 403)

        invalid = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/instances",
            json={"game_key": "unknown", "map_key": "bad-map"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_provider_failure_marks_operation_failed(self):
        instance_provisioning.provider_for = lambda _name, _config: _FakeProvider(fail_message="panel unavailable")
        response = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/instances",
            json={"game_key": "ark_survival_ascended", "map_key": "the_island", "idempotency_key": f"fail-{self.suffix}"},
        )
        self.assertEqual(response.status_code, 202)
        data = response.get_json()
        self.assertEqual(data["server_operation"]["status"], "failed")
        self.assertIn("panel unavailable", data["server_operation"]["result_message"])

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text, email",
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), label),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)


if __name__ == "__main__":
    unittest.main()
