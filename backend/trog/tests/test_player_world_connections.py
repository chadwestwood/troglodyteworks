import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.routes.player_world_connections import (
    normalize_event,
    normalize_short_text,
    status_for_event,
)


class PlayerWorldConnectionTests(unittest.TestCase):
    def test_allowlisted_world_event_is_normalized(self):
        event = normalize_event(
            {
                "event_id": str(uuid4()),
                "event_type": "world.joined",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "world_label": "Friends' Minecraft world",
                    "server_fingerprint": "a" * 64,
                    "connection_kind": "multiplayer",
                },
            }
        )
        self.assertEqual(event["event_type"], "world.joined")
        self.assertEqual(event["payload"]["world_label"], "Friends' Minecraft world")

    def test_raw_log_chat_coordinates_and_server_address_are_rejected(self):
        for prohibited_field in ("raw_log", "chat", "coordinates", "server_address"):
            with self.subTest(prohibited_field=prohibited_field):
                with self.assertRaisesRegex(ValueError, "fields that are not allowed"):
                    normalize_event(
                        {
                            "event_id": str(uuid4()),
                            "event_type": "heartbeat",
                            "occurred_at": datetime.now(timezone.utc).isoformat(),
                            "payload": {prohibited_field: "private"},
                        }
                    )

    def test_unknown_event_type_and_invalid_fingerprint_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "event type"):
            normalize_event(
                {
                    "event_id": str(uuid4()),
                    "event_type": "server.restart",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                }
            )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            normalize_event(
                {
                    "event_id": str(uuid4()),
                    "event_type": "world.joined",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {"server_fingerprint": "play.example.test"},
                }
            )

    def test_connection_status_is_derived_from_event(self):
        self.assertEqual(status_for_event("client.started"), "ready")
        self.assertEqual(status_for_event("world.joined"), "in_world")
        self.assertEqual(status_for_event("world.left"), "ready")
        self.assertEqual(status_for_event("client.stopped"), "offline")

    def test_short_text_rejects_control_characters_and_overflow(self):
        self.assertEqual(normalize_short_text(" My world ", 20), "My world")
        self.assertIsNone(normalize_short_text("bad\nname", 20))
        self.assertIsNone(normalize_short_text("x" * 21, 20))


if __name__ == "__main__":
    unittest.main()
