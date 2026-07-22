import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import g

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config
from twe.routes.instances import get_health, get_instance
from twe.services.nitrado_provider import NitradoRateLimitedError, NitradoUnavailableError


class FakeDatabase:
    def connect(self):
        return FakeConnection()


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class InstanceAuthorizationBoundaryTests(unittest.TestCase):
    @patch("twe.routes.instances.reconcile_instance")
    @patch("twe.routes.instances.instance_access", return_value=None)
    def test_unauthorized_instance_is_rejected_before_reconciliation(
        self, access_mock, reconcile_mock,
    ):
        app = create_app(Config(database_url="postgresql://unused"), database=FakeDatabase())
        with app.test_request_context("/api/v1/instances/other-tenant-instance"):
            g.current_user = {"id": "requesting-user"}
            response, status = get_instance.__wrapped__("other-tenant-instance")

        self.assertEqual(status, 404)
        self.assertEqual(response.get_json()["error"]["code"], "NOT_FOUND")
        access_mock.assert_called_once()
        reconcile_mock.assert_not_called()

    @patch("twe.routes.instances.read_game_server_health", side_effect=NitradoRateLimitedError())
    @patch("twe.routes.instances.resolve_game_server_provider", return_value=object())
    @patch("twe.routes.instances.instance_access", return_value={"game_server_id": "server-id"})
    def test_nitrado_rate_limit_has_stable_safe_response(
        self, _access_mock, _resolve_mock, _health_mock,
    ):
        response, status = self._get_health()

        self.assertEqual(status, 429)
        self.assertEqual(response.get_json()["error"]["code"], "NITRADO_RATE_LIMITED")
        self.assertNotIn("token", response.get_json()["error"]["message"].lower())

    @patch("twe.routes.instances.read_game_server_health", side_effect=NitradoUnavailableError())
    @patch("twe.routes.instances.resolve_game_server_provider", return_value=object())
    @patch("twe.routes.instances.instance_access", return_value={"game_server_id": "server-id"})
    def test_nitrado_outage_is_not_reported_as_application_failure(
        self, _access_mock, _resolve_mock, _health_mock,
    ):
        response, status = self._get_health()

        self.assertEqual(status, 503)
        self.assertEqual(response.get_json()["error"]["code"], "NITRADO_UNAVAILABLE")

    def _get_health(self):
        app = create_app(Config(database_url="postgresql://unused"), database=FakeDatabase())
        with app.test_request_context("/api/v1/instances/instance-id/health"):
            g.current_user = {"id": "requesting-user"}
            return get_health.__wrapped__("instance-id")


if __name__ == "__main__":
    unittest.main()
