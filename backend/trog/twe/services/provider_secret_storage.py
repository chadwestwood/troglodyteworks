from __future__ import annotations

import os
import re
from typing import Mapping, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..db import execute, fetch_one


NONCE_BYTES = 12
MAX_SECRET_BYTES = 16_384
KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ProviderSecretStorageError(RuntimeError):
    code = "PROVIDER_SECRET_STORAGE_ERROR"


class ProviderSecretStorageUnavailable(ProviderSecretStorageError):
    code = "PROVIDER_SECRET_STORAGE_UNAVAILABLE"

    def __init__(self):
        super().__init__(
            "Provider credential storage is unavailable because no approved "
            "authenticated-encryption backend is configured."
        )


class ProviderSecretStorageConfigurationError(ProviderSecretStorageError):
    code = "PROVIDER_SECRET_STORAGE_CONFIGURATION_ERROR"

    def __init__(self):
        super().__init__("Provider credential storage configuration is invalid.")


class ProviderSecretIntegrityError(ProviderSecretStorageError):
    code = "PROVIDER_SECRET_INTEGRITY_ERROR"

    def __init__(self):
        super().__init__("The stored provider credential could not be authenticated.")


class ProviderSecretNotFound(ProviderSecretStorageError):
    code = "PROVIDER_SECRET_NOT_FOUND"

    def __init__(self):
        super().__init__("The provider credential does not exist.")


class ProviderSecretValidationError(ProviderSecretStorageError):
    code = "PROVIDER_SECRET_VALIDATION_ERROR"

    def __init__(self):
        super().__init__("The provider credential is invalid.")


class ProviderSecretStorage(Protocol):
    """Persistence boundary for provider credentials.

    Implementations must use an approved external secret manager or authenticated
    encryption with database-external keys. They must not expose plaintext through
    representations, exceptions, logs, or API responses.
    """

    def store(self, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError

    def replace(self, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError

    def read(self, provider_connection_id: str) -> bytes | None:
        raise NotImplementedError

    def delete(self, provider_connection_id: str) -> None:
        raise NotImplementedError

    def rotate(self, provider_connection_id: str) -> None:
        raise NotImplementedError

    def store_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError

    def replace_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError


class AesGcmProviderSecretCipher:
    """AES-256-GCM envelope cipher with versioned, database-external keys."""

    def __init__(self, keys: Mapping[str, bytes], active_key_version: str):
        copied_keys = dict(keys)
        if (
            not KEY_VERSION_PATTERN.fullmatch(active_key_version or "")
            or active_key_version not in copied_keys
            or not copied_keys
            or any(
                not KEY_VERSION_PATTERN.fullmatch(version)
                or not isinstance(key, bytes)
                or len(key) != 32
                for version, key in copied_keys.items()
            )
        ):
            raise ProviderSecretStorageConfigurationError()
        self._keys = copied_keys
        self.active_key_version = active_key_version

    def encrypt(self, provider_connection_id: str, secret: bytes) -> tuple[bytes, bytes, str]:
        self._validate_secret(secret)
        nonce = os.urandom(NONCE_BYTES)
        version = self.active_key_version
        ciphertext = AESGCM(self._keys[version]).encrypt(
            nonce,
            secret,
            self._associated_data(provider_connection_id, version),
        )
        return ciphertext, nonce, version

    def decrypt(
        self,
        provider_connection_id: str,
        encrypted_payload: bytes,
        encryption_nonce: bytes,
        key_version: str,
    ) -> bytes:
        key = self._keys.get(key_version)
        if key is None or len(encryption_nonce) != NONCE_BYTES:
            raise ProviderSecretStorageConfigurationError()
        try:
            return AESGCM(key).decrypt(
                encryption_nonce,
                encrypted_payload,
                self._associated_data(provider_connection_id, key_version),
            )
        except InvalidTag as exc:
            raise ProviderSecretIntegrityError() from exc

    @staticmethod
    def _associated_data(provider_connection_id: str, key_version: str) -> bytes:
        return f"twe/provider-secret/v1\0{provider_connection_id}\0{key_version}".encode("utf-8")

    @staticmethod
    def _validate_secret(secret: bytes):
        if not isinstance(secret, bytes) or not secret or len(secret) > MAX_SECRET_BYTES:
            raise ProviderSecretValidationError()


class AuthenticatedProviderSecretStorage:
    """PostgreSQL envelope storage protected with authenticated encryption."""

    def __init__(self, database, cipher: AesGcmProviderSecretCipher):
        self._database = database
        self._cipher = cipher

    def store(self, provider_connection_id: str, secret: bytes) -> None:
        with self._database.connect() as conn:
            with conn.transaction():
                self.store_in_transaction(conn, provider_connection_id, secret)

    def store_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        encrypted_payload, nonce, key_version = self._cipher.encrypt(
            provider_connection_id,
            secret,
        )
        execute(
            conn,
            """
            INSERT INTO provider_connection_secrets
                (provider_connection_id, storage_kind, encrypted_payload,
                 encryption_nonce, key_version)
            VALUES (%s, 'encrypted_payload', %s, %s, %s)
            """,
            (provider_connection_id, encrypted_payload, nonce, key_version),
        )

    def replace(self, provider_connection_id: str, secret: bytes) -> None:
        with self._database.connect() as conn:
            with conn.transaction():
                self.replace_in_transaction(conn, provider_connection_id, secret)

    def replace_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        encrypted_payload, nonce, key_version = self._cipher.encrypt(
            provider_connection_id,
            secret,
        )
        updated = fetch_one(
            conn,
            """
            UPDATE provider_connection_secrets
            SET storage_kind = 'encrypted_payload',
                secret_reference = NULL,
                encrypted_payload = %s,
                encryption_nonce = %s,
                key_version = %s,
                rotated_at = now(),
                updated_at = now()
            WHERE provider_connection_id = %s
            RETURNING id::text
            """,
            (encrypted_payload, nonce, key_version, provider_connection_id),
        )
        if not updated:
            raise ProviderSecretNotFound()

    def read(self, provider_connection_id: str) -> bytes | None:
        with self._database.connect() as conn:
            row = fetch_one(
                conn,
                """
                SELECT storage_kind, encrypted_payload, encryption_nonce, key_version
                FROM provider_connection_secrets
                WHERE provider_connection_id = %s
                """,
                (provider_connection_id,),
            )
        if not row:
            return None
        return self._decrypt_row(provider_connection_id, row)

    def _decrypt_row(self, provider_connection_id: str, row) -> bytes:
        if row["storage_kind"] != "encrypted_payload":
            raise ProviderSecretStorageConfigurationError()
        return self._cipher.decrypt(
            provider_connection_id,
            bytes(row["encrypted_payload"]),
            bytes(row["encryption_nonce"]),
            row["key_version"],
        )

    def delete(self, provider_connection_id: str) -> None:
        with self._database.connect() as conn:
            with conn.transaction():
                execute(
                    conn,
                    "DELETE FROM provider_connection_secrets WHERE provider_connection_id = %s",
                    (provider_connection_id,),
                )

    def rotate(self, provider_connection_id: str) -> None:
        with self._database.connect() as conn:
            with conn.transaction():
                row = fetch_one(
                    conn,
                    """
                    SELECT storage_kind, encrypted_payload, encryption_nonce, key_version
                    FROM provider_connection_secrets
                    WHERE provider_connection_id = %s
                    FOR UPDATE
                    """,
                    (provider_connection_id,),
                )
                if not row:
                    raise ProviderSecretNotFound()
                secret = self._decrypt_row(provider_connection_id, row)
                encrypted_payload, nonce, key_version = self._cipher.encrypt(
                    provider_connection_id,
                    secret,
                )
                execute(
                    conn,
                    """
                    UPDATE provider_connection_secrets
                    SET encrypted_payload = %s,
                        encryption_nonce = %s,
                        key_version = %s,
                        rotated_at = now(),
                        updated_at = now()
                    WHERE provider_connection_id = %s
                    """,
                    (encrypted_payload, nonce, key_version, provider_connection_id),
                )


class UnavailableProviderSecretStorage:
    """Fail-closed storage used when no approved keyring is configured."""

    def store(self, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    def replace(self, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    def read(self, provider_connection_id: str) -> bytes | None:
        self._raise_unavailable()

    def delete(self, provider_connection_id: str) -> None:
        self._raise_unavailable()

    def rotate(self, provider_connection_id: str) -> None:
        self._raise_unavailable()

    def store_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    def replace_in_transaction(self, conn, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    @staticmethod
    def _raise_unavailable():
        raise ProviderSecretStorageUnavailable()


def build_provider_secret_storage(config, database) -> ProviderSecretStorage:
    keys_configured = bool(config.provider_secret_keys)
    version_configured = bool(config.provider_secret_active_key_version)
    if not keys_configured and not version_configured:
        return UnavailableProviderSecretStorage()
    if keys_configured != version_configured:
        raise ProviderSecretStorageConfigurationError()
    cipher = AesGcmProviderSecretCipher(
        config.provider_secret_keys,
        config.provider_secret_active_key_version,
    )
    return AuthenticatedProviderSecretStorage(database, cipher)
