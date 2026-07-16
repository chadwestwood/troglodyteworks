import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.rcon import parse_players


class RconPlayerParserTests(unittest.TestCase):
    def test_list_players_returns_only_usernames(self):
        response = (
            "0. Player One, 0002bd9e8123456789abcdef01234567\n"
            "1. PlayerTwo, 76561198012345678\n"
        )
        self.assertEqual(parse_players(response), ["Player One", "PlayerTwo"])

    def test_username_can_contain_a_comma(self):
        response = "3. Last, First, abcdef0123456789abcdef0123456789"
        self.assertEqual(parse_players(response), ["Last, First"])

    def test_unrecognized_row_does_not_discard_username(self):
        self.assertEqual(parse_players("Player Without Identifier"), ["Player Without Identifier"])

    def test_no_players_response_is_empty(self):
        self.assertEqual(parse_players("No Players Connected"), [])


if __name__ == "__main__":
    unittest.main()
