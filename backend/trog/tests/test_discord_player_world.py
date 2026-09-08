import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.discord_bot.core import classify_intent, player_world_status_line


class DiscordPlayerWorldTests(unittest.TestCase):
    def test_minecraft_presence_questions_have_a_distinct_intent(self):
        self.assertEqual(classify_intent("@Trog is Chad playing Minecraft City?"), "player_world_presence")
        self.assertEqual(classify_intent("@Trog Minecraft status"), "player_world_presence")

    def test_presence_reply_is_explicitly_player_observed(self):
        now = datetime.now(timezone.utc)
        reply = player_world_status_line(
            {
                "owner_display_name": "Chad",
                "display_name": "Minecraft City",
                "status": "in_world",
                "last_seen_at": now,
            },
            now=now,
        )
        self.assertIn("currently playing", reply)
        self.assertIn("Trog Client", reply)
        self.assertIn("not by the Minecraft server", reply)

    def test_stale_heartbeat_never_claims_current_presence(self):
        now = datetime.now(timezone.utc)
        reply = player_world_status_line(
            {
                "owner_display_name": "Chad",
                "display_name": "Minecraft City",
                "status": "in_world",
                "last_seen_at": now - timedelta(minutes=4),
            },
            now=now,
        )
        self.assertIn("last heard", reply)
        self.assertIn("cannot confirm", reply)
        self.assertNotIn("currently playing", reply)


if __name__ == "__main__":
    unittest.main()
