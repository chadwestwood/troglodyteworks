import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import g

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config
from twe.routes.instances import get_instance


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


if __name__ == "__main__":
    unittest.main()
