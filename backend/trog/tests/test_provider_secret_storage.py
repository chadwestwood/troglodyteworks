import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.provider_secret_storage import (
    ProviderSecretStorageUnavailable,
    UnavailableProviderSecretStorage,
    build_provider_secret_storage,
)


class ProviderSecretStorageTests(unittest.TestCase):
    def test_default_storage_is_fail_closed(self):
        storage = build_provider_secret_storage()

        self.assertIsInstance(storage, UnavailableProviderSecretStorage)
        with self.assertRaises(ProviderSecretStorageUnavailable) as raised:
            storage.store("connection-id", b"nitrado-token-must-not-leak")

        self.assertEqual(
            raised.exception.code,
            "PROVIDER_SECRET_STORAGE_UNAVAILABLE",
        )
        self.assertNotIn("nitrado-token-must-not-leak", str(raised.exception))
        self.assertNotIn("nitrado-token-must-not-leak", repr(raised.exception))

    def test_every_secret_operation_refuses_without_approved_storage(self):
        storage = UnavailableProviderSecretStorage()
        operations = (
            lambda: storage.store("connection-id", b"new-token"),
            lambda: storage.replace("connection-id", b"replacement-token"),
            lambda: storage.read("connection-id"),
            lambda: storage.delete("connection-id"),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ProviderSecretStorageUnavailable):
                    operation()


if __name__ == "__main__":
    unittest.main()
