from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderConnectionRecord:
    id: str
    community_id: str
    provider_key: str
    display_name: str
    auth_strategy: str
    external_account_id: str | None
    status: str


@dataclass(frozen=True)
class ProviderResourceRecord:
    id: str
    provider_connection_id: str
    resource_type: str
    external_resource_id: str
    display_name: str
    provider_game_key: str | None
    normalized_status: str
    provider_status: str | None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, repr=False)
class ProviderSecretEnvelope:
    storage_kind: str
    secret_reference: str | None = field(default=None, repr=False)
    encrypted_payload: bytes | None = field(default=None, repr=False)
    encryption_nonce: bytes | None = field(default=None, repr=False)
    key_version: str | None = field(default=None, repr=False)
    expires_at: datetime | None = None


class SecretAccessor(Protocol):
    def read_envelope(self) -> ProviderSecretEnvelope | None:
        raise NotImplementedError


@dataclass(frozen=True, repr=False)
class BoundSecretAccessor:
    _envelope: ProviderSecretEnvelope | None = field(default=None, repr=False)

    def read_envelope(self) -> ProviderSecretEnvelope | None:
        return self._envelope


@dataclass(frozen=True)
class TimeoutPolicy:
    connect_seconds: float = 3.0
    read_seconds: float = 8.0


@dataclass(frozen=True)
class ProviderContext:
    connection: ProviderConnectionRecord
    resource: ProviderResourceRecord
    secret_accessor: SecretAccessor = field(repr=False)
    correlation_id: str
    timeout_policy: TimeoutPolicy


@dataclass(frozen=True)
class ConnectionDescription:
    provider_key: str
    display_name: str
    auth_strategy: str


@dataclass(frozen=True)
class DiscoveredResource:
    resource_type: str
    external_resource_id: str
    display_name: str
    provider_game_key: str | None = None
    normalized_status: str = "unknown"
    provider_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class CredentialValidation:
    granted_scopes: tuple[str, ...]


@dataclass(frozen=True)
class CredentialDiscovery:
    resources: tuple[DiscoveredResource, ...]
    total_services: int
    unsupported_services: int
    omitted_services: int


@dataclass(frozen=True)
class ProviderStatusCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class ProviderStatus:
    normalized_status: str
    provider_status: str
    checked_at: str
    checks: tuple[ProviderStatusCheck, ...] = ()

    def as_health_payload(self) -> dict:
        return {
            "overall_status": self.provider_status,
            "checked_at": self.checked_at,
            "checks": [
                {"name": check.name, "status": check.status, "message": check.message}
                for check in self.checks
            ],
        }


class ConnectionDescriber(Protocol):
    def describe_connection(self) -> ConnectionDescription:
        raise NotImplementedError


class ResourceDiscoverer(Protocol):
    def discover_resources(self, context: ProviderContext) -> tuple[DiscoveredResource, ...]:
        raise NotImplementedError


class CredentialValidator(Protocol):
    def validate_credential(self, credential: bytes) -> CredentialValidation:
        raise NotImplementedError


class CredentialResourceDiscoverer(Protocol):
    def discover_resources_with_credential(self, credential: bytes) -> CredentialDiscovery:
        raise NotImplementedError


class StatusReader(Protocol):
    def read_status(self, context: ProviderContext) -> ProviderStatus:
        raise NotImplementedError


class PlayerReader(Protocol):
    def read_players(self, context: ProviderContext) -> dict:
        raise NotImplementedError


class ModReader(Protocol):
    def read_mods(self, context: ProviderContext) -> list[dict[str, str]]:
        raise NotImplementedError
