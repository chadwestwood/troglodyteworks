import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config
from twe.routes.auth import (
    LOGIN_FAILURE_LIMIT,
    LOGIN_RETRY_AFTER_SECONDS,
    login_identifier_hash,
)


class FakeDatabase:
    def __init__(self, user=None):
        self.user = user
        self.failures = {}
        self.sessions = []

    def connect(self):
        return FakeConnection(self)


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class PasswordLoginProtectionTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")

    def test_identifier_hash_is_normalized_and_does_not_expose_email(self):
        first = login_identifier_hash(" Person@Example.COM ")
        second = login_identifier_hash("person@example.com")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotIn("person", first)

    @patch("twe.routes.auth.create_session", return_value="session-token")
    @patch("twe.routes.auth.verify_password")
    @patch("twe.routes.auth.execute")
    @patch("twe.routes.auth.fetch_one")
    def test_failures_lock_identifier_and_success_clears_them(
        self, fetch_mock, execute_mock, verify_mock, _session_mock,
    ):
        user = {
            "id": "user-id", "email": "person@example.com", "display_name": "Person",
            "password_hash": "stored-hash",
        }
        failure_count = 0

        def fetch_side_effect(_conn, query, _params=()):
            nonlocal failure_count
            if "pg_advisory_xact_lock" in query:
                return {"pg_advisory_xact_lock": None}
            if "FROM users" in query:
                return user
            if "FROM password_login_failures" in query:
                return {"count": failure_count}
            raise AssertionError(query)

        def execute_side_effect(_conn, query, _params=()):
            nonlocal failure_count
            if "INSERT INTO password_login_failures" in query:
                failure_count += 1
            elif "DELETE FROM password_login_failures WHERE identifier_hash" in query:
                failure_count = 0
            return None

        fetch_mock.side_effect = fetch_side_effect
        execute_mock.side_effect = execute_side_effect
        verify_mock.side_effect = [False] * LOGIN_FAILURE_LIMIT + [True]
        app = create_app(self.config, database=FakeDatabase(user))
        client = app.test_client()

        responses = [
            client.post("/api/v1/auth/login", json={"email": user["email"], "password": "wrong"})
            for _ in range(LOGIN_FAILURE_LIMIT)
        ]
        blocked = client.post("/api/v1/auth/login", json={"email": user["email"], "password": "correct"})

        self.assertTrue(all(response.status_code == 401 for response in responses[:-1]))
        self.assertEqual(responses[-1].status_code, 429)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers["Retry-After"], str(LOGIN_RETRY_AFTER_SECONDS))
        self.assertEqual(blocked.get_json()["error"]["code"], "LOGIN_RATE_LIMITED")
        # A locked request is rejected before another password hash is evaluated.
        self.assertEqual(verify_mock.call_count, LOGIN_FAILURE_LIMIT)

        failure_count = 0
        success = client.post("/api/v1/auth/login", json={"email": user["email"], "password": "correct"})
        self.assertEqual(success.status_code, 200)
        self.assertEqual(failure_count, 0)

    @patch("twe.routes.auth.verify_password", return_value=False)
    @patch("twe.routes.auth.execute")
    @patch("twe.routes.auth.fetch_one")
    def test_unknown_account_uses_dummy_password_hash_and_generic_error(
        self, fetch_mock, execute_mock, verify_mock,
    ):
        def fetch_side_effect(_conn, query, _params=()):
            if "pg_advisory_xact_lock" in query:
                return {"pg_advisory_xact_lock": None}
            if "FROM users" in query:
                return None
            if "FROM password_login_failures" in query:
                return {"count": 0}
            raise AssertionError(query)

        fetch_mock.side_effect = fetch_side_effect
        app = create_app(self.config, database=FakeDatabase())
        response = app.test_client().post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "INVALID_CREDENTIALS")
        verify_mock.assert_called_once()
        self.assertEqual(execute_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
