import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config, parse_provider_secret_keys
from twe.services.provider_secret_storage import (
    AesGcmProviderSecretCipher,
    AuthenticatedProviderSecretStorage,
    ProviderSecretIntegrityError,
    ProviderSecretNotFound,
    ProviderSecretStorageConfigurationError,
    ProviderSecretStorageUnavailable,
    ProviderSecretValidationError,
    UnavailableProviderSecretStorage,
    build_provider_secret_storage,
)


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def transaction(self):
        return _Transaction()


class _Connect:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


class _Database:
    def __init__(self):
        self.connection = _Connection()

    def connect(self):
        return _Connect(self.connection)


class ProviderSecretCipherTests(unittest.TestCase):
    def setUp(self):
        self.key_v1 = bytes(range(32))
        self.key_v2 = bytes(reversed(range(32)))
        self.cipher = AesGcmProviderSecretCipher({"v1": self.key_v1}, "v1")

    def test_encrypts_and_authenticates_secret_with_unique_nonce(self):
        secret = b"nitrado-token-must-not-leak"
        first = self.cipher.encrypt("connection-id", secret)
        second = self.cipher.encrypt("connection-id", secret)

        self.assertNotEqual(first[0], secret)
        self.assertEqual(len(first[1]), 12)
        self.assertNotEqual(first[1], second[1])
        self.assertEqual(first[2], "v1")
        self.assertEqual(
            self.cipher.decrypt("connection-id", first[0], first[1], first[2]),
            secret,
        )

    def test_tampering_or_connection_substitution_is_rejected_without_secret_leak(self):
        secret = b"nitrado-token-must-not-leak"
        encrypted, nonce, version = self.cipher.encrypt("connection-id", secret)
        tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

        for operation in (
            lambda: self.cipher.decrypt("connection-id", tampered, nonce, version),
            lambda: self.cipher.decrypt("other-connection", encrypted, nonce, version),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(ProviderSecretIntegrityError) as raised:
                    operation()
                self.assertNotIn(secret.decode(), str(raised.exception))
                self.assertNotIn(secret.decode(), repr(raised.exception))

    def test_keyring_reads_old_ciphertext_and_uses_active_key_for_new_writes(self):
        old_encrypted, old_nonce, old_version = self.cipher.encrypt(
            "connection-id",
            b"old-token",
        )
        rotated = AesGcmProviderSecretCipher(
            {"v1": self.key_v1, "v2": self.key_v2},
            "v2",
        )

        self.assertEqual(
            rotated.decrypt("connection-id", old_encrypted, old_nonce, old_version),
            b"old-token",
        )
        self.assertEqual(rotated.encrypt("connection-id", b"new-token")[2], "v2")

    def test_invalid_keys_and_secret_values_fail_with_fixed_errors(self):
        with self.assertRaises(ProviderSecretStorageConfigurationError):
            AesGcmProviderSecretCipher({"v1": b"too-short"}, "v1")
        encrypted, nonce, _version = self.cipher.encrypt("connection-id", b"token")
        with self.assertRaises(ProviderSecretStorageConfigurationError):
            self.cipher.decrypt("connection-id", encrypted, nonce, "missing-version")
        with self.assertRaises(ProviderSecretStorageConfigurationError):
            self.cipher.decrypt("connection-id", encrypted, b"short", "v1")
        for secret in (b"", b"x" * 16_385, "not-bytes"):
            with self.subTest(secret_type=type(secret).__name__):
                with self.assertRaises(ProviderSecretValidationError):
                    self.cipher.encrypt("connection-id", secret)


class ProviderSecretStorageTests(unittest.TestCase):
    def setUp(self):
        self.database = _Database()
        self.cipher = AesGcmProviderSecretCipher({"v1": bytes(range(32))}, "v1")
        self.storage = AuthenticatedProviderSecretStorage(self.database, self.cipher)

    def test_default_storage_is_fail_closed(self):
        storage = build_provider_secret_storage(
            Config(database_url="postgresql://unused"),
            self.database,
        )

        self.assertIsInstance(storage, UnavailableProviderSecretStorage)
        with self.assertRaises(ProviderSecretStorageUnavailable) as raised:
            storage.store("connection-id", b"nitrado-token-must-not-leak")

        self.assertEqual(raised.exception.code, "PROVIDER_SECRET_STORAGE_UNAVAILABLE")
        self.assertNotIn("nitrado-token-must-not-leak", repr(raised.exception))

    def test_configured_factory_builds_authenticated_storage(self):
        config = Config(
            database_url="postgresql://unused",
            provider_secret_active_key_version="v1",
            provider_secret_keys={"v1": bytes(range(32))},
        )
        storage = build_provider_secret_storage(config, self.database)
        self.assertIsInstance(storage, AuthenticatedProviderSecretStorage)
        self.assertNotIn(str(bytes(range(32))), repr(config))

        with self.assertRaises(ProviderSecretStorageConfigurationError):
            build_provider_secret_storage(
                Config(
                    database_url="postgresql://unused",
                    provider_secret_active_key_version="v1",
                ),
                self.database,
            )

    def test_store_writes_only_ciphertext_and_envelope_metadata(self):
        secret = b"nitrado-token-must-not-leak"
        with patch("twe.services.provider_secret_storage.execute") as execute_mock:
            self.storage.store("connection-id", secret)

        params = execute_mock.call_args.args[2]
        self.assertEqual(params[0], "connection-id")
        self.assertNotEqual(params[1], secret)
        self.assertNotIn(secret, params)
        self.assertEqual(len(params[2]), 12)
        self.assertEqual(params[3], "v1")

    def test_read_decrypts_envelope_and_missing_secret_returns_none(self):
        encrypted, nonce, version = self.cipher.encrypt("connection-id", b"stored-token")
        row = {
            "storage_kind": "encrypted_payload",
            "encrypted_payload": encrypted,
            "encryption_nonce": nonce,
            "key_version": version,
        }
        with patch("twe.services.provider_secret_storage.fetch_one", return_value=row):
            self.assertEqual(self.storage.read("connection-id"), b"stored-token")
        with patch("twe.services.provider_secret_storage.fetch_one", return_value=None):
            self.assertIsNone(self.storage.read("connection-id"))

    def test_replace_requires_existing_row_and_never_writes_plaintext(self):
        secret = b"replacement-token"
        with patch(
            "twe.services.provider_secret_storage.fetch_one",
            return_value={"id": "secret-id"},
        ) as fetch_mock:
            self.storage.replace("connection-id", secret)
        params = fetch_mock.call_args.args[2]
        self.assertNotIn(secret, params)
        self.assertEqual(params[-1], "connection-id")

        with patch("twe.services.provider_secret_storage.fetch_one", return_value=None):
            with self.assertRaises(ProviderSecretNotFound):
                self.storage.replace("connection-id", secret)

    def test_delete_can_join_an_existing_transaction(self):
        with patch("twe.services.provider_secret_storage.execute") as execute_mock:
            self.storage.delete_in_transaction(self.database.connection, "connection-id")
        self.assertEqual(execute_mock.call_args.args[2], ("connection-id",))

    def test_every_unavailable_operation_refuses(self):
        storage = UnavailableProviderSecretStorage()
        operations = (
            lambda: storage.store("connection-id", b"new-token"),
            lambda: storage.replace("connection-id", b"replacement-token"),
            lambda: storage.read("connection-id"),
            lambda: storage.delete("connection-id"),
            lambda: storage.rotate("connection-id"),
            lambda: storage.store_in_transaction(self.database.connection, "connection-id", b"token"),
            lambda: storage.replace_in_transaction(self.database.connection, "connection-id", b"token"),
            lambda: storage.delete_in_transaction(self.database.connection, "connection-id"),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ProviderSecretStorageUnavailable):
                    operation()

    def test_keyring_configuration_parses_base64_without_repr_leak(self):
        encoded = base64.b64encode(bytes(range(32))).decode("ascii")
        parsed = parse_provider_secret_keys(f'{{"v1":"{encoded}"}}')
        self.assertEqual(parsed, {"v1": bytes(range(32))})
        with self.assertRaisesRegex(ValueError, "configuration is invalid") as raised:
            parse_provider_secret_keys('{"v1":"not base64!"}')
        self.assertNotIn("not base64", repr(raised.exception))
        self.assertIsNone(raised.exception.__cause__)

    def test_rotate_reencrypts_an_existing_secret_with_the_active_key(self):
        old_cipher = AesGcmProviderSecretCipher({"v1": bytes(range(32))}, "v1")
        encrypted, nonce, version = old_cipher.encrypt("connection-id", b"stored-token")
        rotated_cipher = AesGcmProviderSecretCipher(
            {"v1": bytes(range(32)), "v2": bytes(reversed(range(32)))},
            "v2",
        )
        storage = AuthenticatedProviderSecretStorage(self.database, rotated_cipher)
        row = {
            "storage_kind": "encrypted_payload",
            "encrypted_payload": encrypted,
            "encryption_nonce": nonce,
            "key_version": version,
        }
        with (
            patch(
                "twe.services.provider_secret_storage.fetch_one",
                return_value=row,
            ),
            patch("twe.services.provider_secret_storage.execute") as execute_mock,
        ):
            storage.rotate("connection-id")

        replacement_params = execute_mock.call_args.args[2]
        self.assertEqual(replacement_params[2], "v2")
        self.assertNotIn(b"stored-token", replacement_params)


if __name__ == "__main__":
    unittest.main()
