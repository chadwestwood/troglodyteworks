from __future__ import annotations

from typing import Protocol


class ProviderSecretStorageUnavailable(RuntimeError):
    """Raised when provider credentials cannot be stored safely."""

    code = "PROVIDER_SECRET_STORAGE_UNAVAILABLE"

    def __init__(self):
        super().__init__(
            "Provider credential storage is unavailable because no approved "
            "authenticated-encryption backend is configured."
        )


class ProviderSecretStorage(Protocol):
    """Persistence boundary for provider credentials.

    Implementations must use an approved external secret manager or authenticated
    encryption with keys held outside the application database. Plaintext must
    never be returned from representations, exceptions, logs, or API responses.
    """

    def store(self, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError

    def replace(self, provider_connection_id: str, secret: bytes) -> None:
        raise NotImplementedError

    def read(self, provider_connection_id: str) -> bytes | None:
        raise NotImplementedError

    def delete(self, provider_connection_id: str) -> None:
        raise NotImplementedError


class UnavailableProviderSecretStorage:
    """Fail-closed storage used until a security-approved backend exists."""

    def store(self, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    def replace(self, provider_connection_id: str, secret: bytes) -> None:
        self._raise_unavailable()

    def read(self, provider_connection_id: str) -> bytes | None:
        self._raise_unavailable()

    def delete(self, provider_connection_id: str) -> None:
        self._raise_unavailable()

    @staticmethod
    def _raise_unavailable():
        raise ProviderSecretStorageUnavailable()


def build_provider_secret_storage() -> ProviderSecretStorage:
    """Return the configured secret backend.

    There is intentionally no configuration branch yet: the repository has no
    approved authenticated-encryption or external-secret-manager integration.
    """

    return UnavailableProviderSecretStorage()
