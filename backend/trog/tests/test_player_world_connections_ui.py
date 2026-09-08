import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config


class PlayerWorldConnectionsUITests(unittest.TestCase):
    def test_community_exposes_non_hosting_world_connection_journey(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        community = client.get("/communities/cohorts-in-the-wild/")
        page = client.get("/communities/cohorts-in-the-wild/world-connections/")
        script = client.get("/js/player-world-connections.js")

        self.assertEqual(community.status_code, 200)
        self.assertIn(b"Connect a world you play in", community.data)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"does not claim that you host", page.data)
        self.assertIn(b"Raw", page.data)
        self.assertIn(b"logs", page.data)
        self.assertIn(b"player-world-connections", script.data)
        self.assertIn(b"navigator.clipboard.writeText", script.data)
        self.assertIn(b"Two-sided approval", page.data)
        self.assertIn(b"discord-bindings", script.data)
        self.assertNotIn(b"localStorage", script.data)


if __name__ == "__main__":
    unittest.main()
