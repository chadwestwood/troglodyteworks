import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.services.mcp_tools import McpReadTools, McpToolError


class FakeDatabase:
    @contextmanager
    def connect(self):
        yield object()


class McpReadToolTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"user_id": "user-1", "email": "user@example.test"}
        self.access = {
            "instance_id": "11111111-1111-1111-1111-111111111111",
            "instance_name": "Genesis",
            "instance_slug": "genesis",
            "game_server_id": "22222222-2222-2222-2222-222222222222",
            "game_server_name": "ARK Survival Ascended",
            "community_id": "33333333-3333-3333-3333-333333333333",
            "community_name": "Cohorts in the Wild",
            "membership_id": "44444444-4444-4444-4444-444444444444",
            "role": "member",
        }
        self.tools = McpReadTools(FakeDatabase(), Config(database_url="postgresql://unused"))

    @patch("twe.services.mcp_tools.execute")
    @patch("twe.services.mcp_tools.instance_access", return_value=None)
    def test_cross_tenant_instance_is_hidden_and_audited(self, _access, audit):
        with self.assertRaises(McpToolError) as error:
            self.tools.get_operation_history(
                self.identity,
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            )
        self.assertEqual(error.exception.code, "NOT_FOUND")
        self.assertIn("mcp.tool.called", audit.call_args.args[1])

    @patch("twe.services.mcp_tools.execute")
    @patch("twe.services.mcp_tools.resolve_game_server_provider", return_value=object())
    @patch("twe.services.mcp_tools.can_request_capability", return_value=False)
    @patch("twe.services.mcp_tools.instance_access")
    def test_capability_denial_happens_before_provider_read(
        self, access, _capability, _resolution, _audit,
    ):
        access.return_value = self.access
        with patch("twe.services.mcp_tools.read_game_server_health") as provider_read:
            with self.assertRaises(McpToolError) as error:
                self.tools.get_server_status(self.identity, self.access["instance_id"])
        self.assertEqual(error.exception.code, "FORBIDDEN")
        provider_read.assert_not_called()

    @patch("twe.services.mcp_tools.execute")
    @patch("twe.services.mcp_tools.read_game_server_players")
    @patch("twe.services.mcp_tools.resolve_game_server_provider", return_value=object())
    @patch("twe.services.mcp_tools.can_request_capability")
    @patch("twe.services.mcp_tools.instance_access")
    def test_player_names_are_withheld_without_name_capability(
        self, access, capability, _resolution, read_players, _audit,
    ):
        access.return_value = self.access
        capability.side_effect = lambda _access, key, _conn: key == "instance.players.count.read"
        read_players.return_value = {"count": 1, "players": ["PrivatePlayerName"]}
        result = self.tools.get_active_players(self.identity, self.access["instance_id"])
        self.assertEqual(result["active_players"]["count"], 1)
        self.assertFalse(result["active_players"]["names_included"])
        self.assertNotIn("players", result["active_players"])

    @patch("twe.services.mcp_tools.execute")
    @patch("twe.services.mcp_tools.read_game_server_mods")
    @patch("twe.services.mcp_tools.resolve_game_server_provider", return_value=object())
    @patch("twe.services.mcp_tools.can_request_capability", return_value=True)
    @patch("twe.services.mcp_tools.instance_access")
    def test_mods_return_structured_tenant_context(
        self, access, _capability, _resolution, read_mods, _audit,
    ):
        access.return_value = self.access
        read_mods.return_value = [{"id": "930381", "name": "Silent Structures"}]
        result = self.tools.get_installed_mods(self.identity, self.access["instance_id"])
        self.assertEqual(result["context"]["community"]["name"], "Cohorts in the Wild")
        self.assertEqual(result["context"]["instance"]["id"], self.access["instance_id"])
        self.assertEqual(result["mods"][0]["name"], "Silent Structures")


if __name__ == "__main__":
    unittest.main()

