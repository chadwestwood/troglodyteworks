import os
import unittest
from unittest.mock import patch

from scripts.verify_secret_inventory import PROFILES, inventory


class SecretInventoryTests(unittest.TestCase):
    def test_missing_names_are_reported_without_values(self):
        with patch.dict(os.environ, {}, clear=True):
            present, missing = inventory("worker")
        self.assertEqual(present, [])
        self.assertEqual(missing, list(PROFILES["worker"]))

    def test_present_names_are_reported_by_name(self):
        values = {name: f"value-for-{name}" for name in PROFILES["worker"]}
        with patch.dict(os.environ, values, clear=True):
            present, missing = inventory("worker")
        self.assertEqual(present, list(PROFILES["worker"]))
        self.assertEqual(missing, [])
