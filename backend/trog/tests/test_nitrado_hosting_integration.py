import json
import secrets
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import load_config
from twe.db import Database, execute, fetch_all, fetch_one
from twe.routes.auth import create_session
from twe.security import hash_password
from twe.services.nitrado_provider import NitradoHttpResponse
from twe.services.provider_registry import build_provider_registry


class _Transport:
    def __init__(self, services=None, status=200, body=None):
        self.services = services if services is not None else []
        self.status = status
        self.body = body
        self.calls = []

    def get(self, url, headers, timeout_seconds):
        self.calls.append((url, headers, timeout_seconds))
        body = self.body
        if body is None:
            body = json.dumps({"status": "success", "data": {"services": self.services}}).encode()
        return NitradoHttpResponse(status=self.status, body=body)


class NitradoHostingIntegrationTests(unittest.TestCase):
    def setUp(self):
        loaded = load_config()
        self.config = replace(
            loaded,
            provider_secret_active_key_version="integration-v1",
            provider_secret_keys={"integration-v1": secrets.token_bytes(32)},
        )
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        self.transport = _Transport(self._services())
        try:
            with self.db.connect() as conn:
                if not fetch_one(
                    conn,
                    "SELECT to_regclass('idx_provider_connections_one_nitrado_per_community') IS NOT NULL AS present",
                )["present"]:
                    raise unittest.SkipTest("Nitrado Slice 2B migration is not applied.")
                self.owner = self._user(conn, "owner")
                self.member = self._user(conn, "member")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Nitrado {self.suffix}", f"nitrado-{self.suffix}", self.owner["id"]),
                )
                self._membership(conn, self.owner["id"], "owner")
                self._membership(conn, self.member["id"], "member")
                registry = build_provider_registry(self.config, self.transport)
                self.app = create_app(self.config, database=self.db, provider_registry=registry)
                self.owner_client = self.app.test_client()
                self.member_client = self.app.test_client()
                self._login(conn, self.owner_client, self.owner["id"])
                self._login(conn, self.member_client, self.member["id"])
        except unittest.SkipTest:
            raise
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for Nitrado integration test: {exc.__class__.__name__}")

    def tearDown(self):
        if not hasattr(self, "community"):
            return
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s)", (self.owner["id"], self.member["id"]))

    def test_owner_connects_discovers_and_retries_without_duplicates_or_secret_leaks(self):
        token = f"nitrado-secret-{self.suffix}"
        first = self._connect(token)
        self.assertEqual(first.status_code, 201)
        data = first.get_json()
        connection_id = data["connection"]["id"]
        self.assertEqual(data["connection"]["granted_scopes"], ["service"])
        self.assertEqual(data["connection"]["credential"], {"configured": True, "masked": True})
        self.assertEqual(data["discovery"]["supported_services"], 1)
        self.assertEqual(data["discovery"]["unsupported_services"], 1)
        self.assertEqual(data["discovery"]["omitted_services"], 1)
        self.assertNotIn(token, first.get_data(as_text=True))

        with self.db.connect() as conn:
            envelope = fetch_one(
                conn,
                "SELECT encrypted_payload, encryption_nonce FROM provider_connection_secrets WHERE provider_connection_id = %s",
                (connection_id,),
            )
            counts = fetch_one(
                conn,
                """
                SELECT (SELECT count(*) FROM provider_connections WHERE community_id = %s AND provider_key = 'nitrado') AS connections,
                       (SELECT count(*) FROM provider_connection_secrets WHERE provider_connection_id = %s) AS secrets,
                       (SELECT count(*) FROM provider_resources WHERE provider_connection_id = %s) AS resources
                """,
                (self.community["id"], connection_id, connection_id),
            )
            audit_text = " ".join(
                json.dumps(row["details"]) for row in fetch_all(
                    conn,
                    "SELECT details FROM audit_logs WHERE community_id = %s AND target_id = %s",
                    (self.community["id"], connection_id),
                )
            )
        self.assertNotIn(token.encode(), bytes(envelope["encrypted_payload"]))
        self.assertEqual(len(envelope["encryption_nonce"]), 12)
        self.assertEqual(dict(counts), {"connections": 1, "secrets": 1, "resources": 2})
        self.assertNotIn(token, audit_text)

        retry = self._connect(token)
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.get_json()["connection"]["id"], connection_id)
        with self.db.connect() as conn:
            retry_counts = fetch_one(
                conn,
                """
                SELECT (SELECT count(*) FROM provider_connections WHERE community_id = %s AND provider_key = 'nitrado') AS connections,
                       (SELECT count(*) FROM provider_connection_secrets WHERE provider_connection_id = %s) AS secrets,
                       (SELECT count(*) FROM provider_resources WHERE provider_connection_id = %s) AS resources
                """,
                (self.community["id"], connection_id, connection_id),
            )
        self.assertEqual(dict(retry_counts), {"connections": 1, "secrets": 1, "resources": 2})

    def test_csrf_and_non_owner_requests_are_rejected_before_provider_call(self):
        missing_csrf = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/nitrado",
            json={"token": "token"},
        )
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(missing_csrf.get_json()["error"]["code"], "CSRF_REJECTED")

        forbidden = self.member_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/nitrado",
            json={"token": "token"},
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(len(self.transport.calls), 0)

    def test_stored_token_discovery_updates_availability_and_resources_endpoint(self):
        created = self._connect("stored-token")
        connection_id = created.get_json()["connection"]["id"]
        self.transport.services = []

        discovered = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/discover",
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(discovered.status_code, 200)
        self.assertEqual(discovered.get_json()["discovery"]["total_services"], 0)
        self.assertTrue(all(not row["available"] for row in discovered.get_json()["discovery"]["resources"]))

        listed = self.owner_client.get(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/resources"
        )
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(all(not row["available"] for row in listed.get_json()["resources"]))

        member_discovery = self.member_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/discover",
            headers={"X-TWE-CSRF": "1"},
        )
        member_resources = self.member_client.get(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/resources"
        )
        self.assertEqual(member_discovery.status_code, 403)
        self.assertEqual(member_resources.status_code, 403)

    def test_owner_selects_supported_resource_and_binding_is_idempotent_and_visible(self):
        connected = self._connect("binding-token").get_json()
        connection_id = connected["connection"]["id"]
        resource = next(row for row in connected["discovery"]["resources"] if row["supported"])
        with self.db.connect() as conn:
            game_server = self._game_server(conn, "asa")
            other_server = self._game_server(conn, "other")

        missing_csrf = self.owner_client.post(
            self._selection_path(connection_id, resource["id"]),
            json={"game_server_id": game_server["id"]},
        )
        forbidden = self.member_client.post(
            self._selection_path(connection_id, resource["id"]),
            json={"game_server_id": game_server["id"]},
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(missing_csrf.get_json()["error"]["code"], "CSRF_REJECTED")
        self.assertEqual(forbidden.get_json()["error"]["code"], "FORBIDDEN")

        first = self._select(connection_id, resource["id"], game_server["id"])
        self.assertEqual(first.status_code, 200)
        binding = first.get_json()["binding"]
        self.assertFalse(binding["already_bound"])
        self.assertEqual(binding["game_server"]["provider_resource_id"], resource["id"])
        self.assertEqual(binding["game_server"]["game_key"], "ark_survival_ascended")
        self.assertEqual(binding["resource"]["binding"]["game_server_id"], game_server["id"])
        selected_at = binding["resource"]["selected_at"]

        repeated = self._select(connection_id, resource["id"], game_server["id"])
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.get_json()["binding"]["already_bound"])
        self.assertEqual(repeated.get_json()["binding"]["resource"]["selected_at"], selected_at)

        conflict = self._select(connection_id, resource["id"], other_server["id"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.get_json()["error"]["code"], "PROVIDER_RESOURCE_ALREADY_BOUND")

        listed = self.owner_client.get(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/resources"
        ).get_json()["resources"]
        listed_resource = next(row for row in listed if row["id"] == resource["id"])
        self.assertEqual(listed_resource["binding"]["game_server_id"], game_server["id"])
        with self.db.connect() as conn:
            audit_count = fetch_one(
                conn,
                """
                SELECT count(*)::int AS count
                FROM audit_logs
                WHERE community_id = %s AND action = 'provider.resource.selected'
                  AND target_type = 'game_server' AND target_id = %s
                """,
                (self.community["id"], game_server["id"]),
            )["count"]
        self.assertEqual(audit_count, 1)

    def test_selection_rejects_unsupported_unavailable_mismatched_and_existing_bindings(self):
        connected = self._connect("selection-validation-token").get_json()
        connection_id = connected["connection"]["id"]
        supported = next(row for row in connected["discovery"]["resources"] if row["supported"])
        unsupported = next(row for row in connected["discovery"]["resources"] if not row["supported"])
        with self.db.connect() as conn:
            ark_server = self._game_server(conn, "ark")
            minecraft_server = self._game_server(conn, "minecraft", game_type="Minecraft", game_key="minecraft")
            unavailable = self._provider_resource(conn, connection_id, "unavailable", available=False)
            second_resource = self._provider_resource(conn, connection_id, "second")

        mismatch = self._select(connection_id, supported["id"], minecraft_server["id"])
        self.assertEqual(mismatch.get_json()["error"]["code"], "GAME_SERVER_GAME_MISMATCH")
        unsupported_response = self._select(connection_id, unsupported["id"], ark_server["id"])
        self.assertEqual(unsupported_response.get_json()["error"]["code"], "PROVIDER_RESOURCE_UNSUPPORTED")
        unavailable_response = self._select(connection_id, unavailable["id"], ark_server["id"])
        self.assertEqual(unavailable_response.get_json()["error"]["code"], "PROVIDER_RESOURCE_UNAVAILABLE")

        self.assertEqual(self._select(connection_id, supported["id"], ark_server["id"]).status_code, 200)
        server_conflict = self._select(connection_id, second_resource["id"], ark_server["id"])
        self.assertEqual(server_conflict.status_code, 409)
        self.assertEqual(server_conflict.get_json()["error"]["code"], "GAME_SERVER_ALREADY_BOUND")

        with self.db.connect() as conn:
            execute(
                conn,
                "UPDATE provider_connections SET status = 'reauthorization_required' WHERE id = %s",
                (connection_id,),
            )
        inactive = self._select(connection_id, second_resource["id"], ark_server["id"])
        self.assertEqual(inactive.status_code, 409)
        self.assertEqual(inactive.get_json()["error"]["code"], "HOSTING_CONNECTION_NOT_ACTIVE")

    def test_revoked_stored_token_marks_connection_for_reauthorization(self):
        created = self._connect("soon-revoked-token")
        connection_id = created.get_json()["connection"]["id"]
        self.transport.status = 401

        response = self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/{connection_id}/discover",
            headers={"X-TWE-CSRF": "1"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "NITRADO_AUTHENTICATION_FAILED")
        with self.db.connect() as conn:
            connection = fetch_one(
                conn,
                "SELECT status, last_error_code FROM provider_connections WHERE id = %s",
                (connection_id,),
            )
        self.assertEqual(connection["status"], "reauthorization_required")
        self.assertEqual(connection["last_error_code"], "NITRADO_AUTHENTICATION_FAILED")

    def test_invalid_token_and_provider_errors_do_not_persist_connection(self):
        cases = ((401, "NITRADO_AUTHENTICATION_FAILED"), (403, "NITRADO_INSUFFICIENT_SCOPE"),
                 (429, "NITRADO_RATE_LIMITED"), (503, "NITRADO_UNAVAILABLE"))
        for status, code in cases:
            with self.subTest(status=status):
                self.transport.status = status
                response = self._connect("rejected-token")
                self.assertEqual(response.get_json()["error"]["code"], code)
                with self.db.connect() as conn:
                    count = fetch_one(
                        conn,
                        "SELECT count(*)::int AS count FROM provider_connections WHERE community_id = %s AND provider_key = 'nitrado'",
                        (self.community["id"],),
                    )["count"]
                self.assertEqual(count, 0)

    def _connect(self, token):
        return self.owner_client.post(
            f"/api/v1/communities/{self.community['id']}/hosting-connections/nitrado",
            json={"token": token},
            headers={"X-TWE-CSRF": "1"},
        )

    def _selection_path(self, connection_id, resource_id):
        return (
            f"/api/v1/communities/{self.community['id']}/hosting-connections/"
            f"{connection_id}/resources/{resource_id}/select"
        )

    def _select(self, connection_id, resource_id, game_server_id):
        return self.owner_client.post(
            self._selection_path(connection_id, resource_id),
            json={"game_server_id": game_server_id},
            headers={"X-TWE-CSRF": "1"},
        )

    def _game_server(self, conn, label, game_type="ARK Survival Ascended", game_key=None):
        return fetch_one(
            conn,
            """
            INSERT INTO game_servers
                (community_id, name, slug, game_type, management_adapter, game_key)
            VALUES (%s, %s, %s, %s, 'nitrado', %s)
            RETURNING id::text
            """,
            (self.community["id"], f"Server {label}", f"server-{label}-{self.suffix}", game_type, game_key),
        )

    def _provider_resource(self, conn, connection_id, label, available=True):
        return fetch_one(
            conn,
            """
            INSERT INTO provider_resources
                (provider_connection_id, resource_type, external_resource_id,
                 display_name, provider_game_key, available)
            VALUES (%s, 'game_server_service', %s, %s, 'ark_survival_ascended', %s)
            RETURNING id::text
            """,
            (connection_id, f"service-{label}-{self.suffix}", f"Service {label}", available),
        )

    def _services(self):
        return [
            {"id": 101, "type": "gameserver", "status": "active",
             "details": {"name": "ASA Friends", "game": "ARK: Survival Ascended", "game_slots": 20}},
            {"id": 102, "type": "gameserver", "status": "active",
             "details": {"name": "Minecraft", "game": "Minecraft", "game_slots": 10}},
            {"id": 103, "type": "voiceserver", "status": "active"},
        ]

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text",
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), label),
        )

    def _membership(self, conn, user_id, role):
        execute(
            conn,
            "INSERT INTO community_memberships (user_id, community_id, role) VALUES (%s,%s,%s)",
            (user_id, self.community["id"], role),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)


if __name__ == "__main__":
    unittest.main()
