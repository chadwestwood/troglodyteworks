import unittest
from contextlib import contextmanager
from unittest.mock import patch

from starlette.testclient import TestClient

from twe.config import Config
from twe.mcp_server import authenticated_mcp_app


class FakeDatabase:
    @contextmanager
    def connect(self):
        yield object()


class McpProtocolTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            database_url="postgresql://unused",
            mcp_allowed_hosts=("testserver",),
        )
        self.headers = {
            "Authorization": "Bearer twe_mcp_protocol-test",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

    def test_mcp_requires_bearer_token(self):
        app = authenticated_mcp_app(self.config, FakeDatabase())
        with TestClient(app) as client:
            response = client.post("/mcp", json=self._initialize())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "UNAUTHENTICATED")

    @patch("twe.mcp_server.execute")
    @patch(
        "twe.mcp_server.fetch_one",
        return_value={
            "user_id": "user-1",
            "email": "user@example.test",
            "display_name": "User",
            "token_id": "token-1",
        },
    )
    def test_server_initializes_and_lists_only_read_tools(self, _token, _touch):
        app = authenticated_mcp_app(self.config, FakeDatabase())
        with TestClient(app) as client:
            initialized = client.post("/mcp", headers=self.headers, json=self._initialize())
            listed = client.post(
                "/mcp",
                headers=self.headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
        self.assertEqual(initialized.status_code, 200)
        self.assertEqual(initialized.json()["result"]["serverInfo"]["name"], "Troglodyte Works")
        names = [tool["name"] for tool in listed.json()["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "twe_list_instances",
                "twe_get_server_status",
                "twe_get_active_players",
                "twe_get_installed_mods",
                "twe_get_operation_history",
            ],
        )
        self.assertFalse(any("restart" in name or "write" in name for name in names))

    @staticmethod
    def _initialize():
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "TWE test client", "version": "1"},
            },
        }


if __name__ == "__main__":
    unittest.main()

