import asyncio
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.discord_bot.service import worker_heartbeat_loop
from twe.services.runtime_heartbeat import runtime_heartbeat_response


class RuntimeHeartbeatTests(unittest.TestCase):
    def test_stale_worker_is_reported_without_exposing_extra_details(self):
        now = datetime(2026, 7, 22, tzinfo=timezone.utc)
        rows = [{
            "component": "trog_worker",
            "status": "ready",
            "checked_at": now - timedelta(seconds=121),
            "details": {"guild_count": 1, "guild_ids": ["must-not-survive"]},
        }]

        result = runtime_heartbeat_response(rows, now=now)[0]

        self.assertEqual(result["status"], "stale")
        self.assertEqual(result["reported_status"], "ready")
        self.assertEqual(result["details"], {"guild_count": 1})
        self.assertNotIn("must-not-survive", repr(result))

    def test_recent_worker_is_ready(self):
        now = datetime(2026, 7, 22, tzinfo=timezone.utc)
        result = runtime_heartbeat_response([{
            "component": "trog_worker",
            "status": "ready",
            "checked_at": now - timedelta(seconds=30),
            "details": {"guild_count": 2},
        }], now=now)[0]

        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["age_seconds"], 30)

    @patch("twe.discord_bot.service.asyncio.sleep")
    @patch("twe.discord_bot.service.record_runtime_heartbeat")
    def test_worker_records_only_count_and_connection_state(self, record_mock, sleep_mock):
        client = Mock()
        client.is_closed.side_effect = [False, True]
        client.is_ready.return_value = True
        client.guilds = [Mock(), Mock()]
        database = Mock()
        database.connect.return_value = MagicMock()
        connection = Mock()
        database.connect.return_value.__enter__.return_value = connection

        asyncio.run(worker_heartbeat_loop(client, database, interval_seconds=0))

        record_mock.assert_called_once_with(
            connection, "trog_worker", "ready", {"guild_count": 2},
        )
        sleep_mock.assert_awaited_once_with(0)


if __name__ == "__main__":
    unittest.main()
