from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .provider_contracts import (
    ConnectionDescription,
    CredentialDiscovery,
    CredentialValidation,
    DiscoveredResource,
    ProviderContext,
    ProviderStatus,
    ProviderStatusCheck,
)
from .provider_secret_storage import AesGcmProviderSecretCipher


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NitradoProviderError(RuntimeError):
    code = "NITRADO_ERROR"
    http_status = 502


class NitradoAuthenticationError(NitradoProviderError):
    code = "NITRADO_AUTHENTICATION_FAILED"
    http_status = 401

    def __init__(self):
        super().__init__("The Nitrado token is invalid, expired, or revoked.")


class NitradoInsufficientScopeError(NitradoProviderError):
    code = "NITRADO_INSUFFICIENT_SCOPE"
    http_status = 403

    def __init__(self):
        super().__init__("The Nitrado token must include the service scope.")


class NitradoRateLimitedError(NitradoProviderError):
    code = "NITRADO_RATE_LIMITED"
    http_status = 429

    def __init__(self):
        super().__init__("Nitrado is rate limiting requests. Try again later.")


class NitradoUnavailableError(NitradoProviderError):
    code = "NITRADO_UNAVAILABLE"
    http_status = 503

    def __init__(self):
        super().__init__("Nitrado is temporarily unavailable. Try again later.")


class NitradoMalformedResponseError(NitradoProviderError):
    code = "NITRADO_MALFORMED_RESPONSE"
    http_status = 502

    def __init__(self):
        super().__init__("Nitrado returned an unexpected response.")


@dataclass(frozen=True, repr=False)
class NitradoHttpResponse:
    status: int
    body: bytes = field(repr=False)


class NitradoHttpTransport:
    def get(self, url: str, headers: dict[str, str], timeout_seconds: float) -> NitradoHttpResponse:
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise NitradoMalformedResponseError()
                return NitradoHttpResponse(status=response.status, body=body)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            return NitradoHttpResponse(status=status, body=b"")
        except (TimeoutError, socket.timeout, URLError) as exc:
            raise NitradoUnavailableError() from exc


@dataclass(frozen=True)
class NitradoService:
    service_id: str
    service_type: str
    status: str
    display_name: str
    game_title: str | None
    game_key_hint: str | None
    slots: int | None
    address: str | None
    location_id: str | None
    suspend_date: str | None


class NitradoClient:
    def __init__(self, base_url: str, timeout_seconds: float, transport=None):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport or NitradoHttpTransport()

    def list_services(self, credential: bytes) -> tuple[NitradoService, ...]:
        response = self._get("/services", credential)
        return self._parse_services(response.body)

    def get_gameserver_status(self, service_id: str, credential: bytes) -> str:
        if not service_id.isdigit():
            raise NitradoMalformedResponseError()
        response = self._get(f"/services/{service_id}/gameservers", credential)
        return self._parse_gameserver_status(response.body)

    def _get(self, path: str, credential: bytes) -> NitradoHttpResponse:
        try:
            token = credential.decode("ascii")
        except (AttributeError, UnicodeDecodeError):
            raise NitradoAuthenticationError() from None
        response = self._transport.get(
            f"{self._base_url}{path}",
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "Troglodyte-Works/1.0",
            },
            self._timeout_seconds,
        )
        if response.status == 401:
            raise NitradoAuthenticationError()
        if response.status == 403:
            raise NitradoInsufficientScopeError()
        if response.status == 429:
            raise NitradoRateLimitedError()
        if response.status >= 500:
            raise NitradoUnavailableError()
        if response.status != 200:
            raise NitradoMalformedResponseError()
        return response

    @staticmethod
    def _parse_services(body: bytes) -> tuple[NitradoService, ...]:
        try:
            payload = json.loads(body)
            if payload.get("status") != "success":
                raise ValueError
            rows = payload["data"]["services"]
            if not isinstance(rows, list):
                raise ValueError
            services = []
            for row in rows:
                if not isinstance(row, dict) or isinstance(row.get("id"), bool):
                    raise ValueError
                service_id = str(row["id"]).strip()
                if not service_id or not service_id.isdigit():
                    raise ValueError
                details = row.get("details") or {}
                if not isinstance(details, dict):
                    raise ValueError
                slots = details.get("game_slots", details.get("slots"))
                if slots is not None and (isinstance(slots, bool) or not isinstance(slots, int)):
                    slots = None
                display_name = _safe_text(details.get("name")) or _safe_text(row.get("comment"))
                display_name = display_name or _safe_text(row.get("type_human")) or f"Nitrado service {service_id}"
                services.append(
                    NitradoService(
                        service_id=service_id,
                        service_type=_safe_text(row.get("type")) or "unknown",
                        status=_safe_text(row.get("status")) or "unknown",
                        display_name=display_name,
                        game_title=_safe_text(details.get("game")),
                        game_key_hint=_safe_text(details.get("folder_short")) or _safe_text(details.get("portlist_short")),
                        slots=slots,
                        address=_safe_text(details.get("address")),
                        location_id=_safe_text(row.get("location_id")),
                        suspend_date=_safe_text(row.get("suspend_date")),
                    )
                )
            return tuple(services)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise NitradoMalformedResponseError() from None

    @staticmethod
    def _parse_gameserver_status(body: bytes) -> str:
        try:
            payload = json.loads(body)
            if payload.get("status") != "success":
                raise ValueError
            data = payload["data"]
            if not isinstance(data, dict):
                raise ValueError
            gameserver = data.get("gameserver")
            if gameserver is None:
                gameservers = data.get("gameservers")
                if not isinstance(gameservers, list) or len(gameservers) != 1:
                    raise ValueError
                gameserver = gameservers[0]
            if not isinstance(gameserver, dict):
                raise ValueError
            status = _safe_text(gameserver.get("status"))
            if not status:
                raise ValueError
            return status.lower()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise NitradoMalformedResponseError() from None


class NitradoProvider:
    def __init__(self, config, transport=None):
        self._config = config
        self._client = NitradoClient(
            config.nitrado_api_base_url,
            config.nitrado_timeout_seconds,
            transport=transport,
        )

    def describe_connection(self) -> ConnectionDescription:
        return ConnectionDescription(
            provider_key="nitrado",
            display_name="Nitrado",
            auth_strategy="configuration",
        )

    def validate_credential(self, credential: bytes) -> CredentialValidation:
        self._client.list_services(credential)
        return CredentialValidation(granted_scopes=("service",))

    def discover_resources_with_credential(self, credential: bytes) -> CredentialDiscovery:
        services = self._client.list_services(credential)
        resources = []
        seen_ids = set()
        unsupported = 0
        omitted = 0
        for service in services:
            if service.service_id in seen_ids:
                continue
            seen_ids.add(service.service_id)
            if service.service_type != "gameserver":
                omitted += 1
                continue
            supported = _canonical_game_title(service.game_title) == "ark survival ascended"
            if not supported:
                unsupported += 1
            metadata = {
                key: value
                for key, value in {
                    "service_id": service.service_id,
                    "game_title": service.game_title,
                    "provider_game_key": service.game_key_hint,
                    "slots": service.slots,
                    "public_address": service.address,
                    "location_id": service.location_id,
                    "expiration_date": service.suspend_date,
                }.items()
                if value is not None
            }
            resources.append(
                DiscoveredResource(
                    resource_type="game_server_service",
                    external_resource_id=service.service_id,
                    display_name=service.display_name,
                    provider_game_key="ark_survival_ascended" if supported else None,
                    normalized_status=_normalized_status(service.status),
                    provider_status=service.status,
                    metadata=metadata,
                )
            )
        return CredentialDiscovery(
            resources=tuple(resources),
            total_services=len(services),
            unsupported_services=unsupported,
            omitted_services=omitted,
        )

    def read_status(self, context: ProviderContext) -> ProviderStatus:
        if context.connection.provider_key != "nitrado":
            raise ValueError("Nitrado adapter received the wrong Provider Connection.")
        credential = self._credential(context)
        provider_status = self._client.get_gameserver_status(
            context.resource.external_resource_id,
            credential,
        )
        health_status = _normalized_gameserver_status(provider_status)
        normalized_status = "online" if health_status == "ready" else health_status
        check_status = "passed" if health_status == "ready" else health_status
        return ProviderStatus(
            normalized_status=normalized_status,
            provider_status=health_status,
            checked_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            checks=(
                ProviderStatusCheck(
                    name="nitrado_gameserver",
                    status=check_status,
                    message=f"Nitrado reports the game server as {provider_status}.",
                ),
            ),
        )

    def _credential(self, context: ProviderContext) -> bytes:
        envelope = context.secret_accessor.read_envelope()
        if (
            envelope is None
            or envelope.storage_kind != "encrypted_payload"
            or envelope.encrypted_payload is None
            or envelope.encryption_nonce is None
            or not envelope.key_version
        ):
            raise NitradoAuthenticationError()
        if envelope.expires_at is not None:
            expires_at = envelope.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= datetime.now(timezone.utc):
                raise NitradoAuthenticationError()
        cipher = AesGcmProviderSecretCipher(
            self._config.provider_secret_keys,
            self._config.provider_secret_active_key_version,
        )
        return cipher.decrypt(
            context.connection.id,
            bytes(envelope.encrypted_payload),
            bytes(envelope.encryption_nonce),
            envelope.key_version,
        )


def _safe_text(value) -> str | None:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    rendered = str(value).strip()
    return rendered[:500] if rendered else None


def _canonical_game_title(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _normalized_status(status: str) -> str:
    return {
        "installing": "starting",
        "suspended": "offline",
        "adminlocked": "failed",
        "adminlocked_suspended": "failed",
    }.get(status, "unknown")


def _normalized_gameserver_status(status: str) -> str:
    return {
        "started": "ready",
        "running": "ready",
        "online": "ready",
        "stopped": "offline",
        "offline": "offline",
        "suspended": "offline",
        "suspended_manually": "offline",
        "starting": "degraded",
        "restarting": "degraded",
        "stopping": "degraded",
        "installing": "degraded",
        "updating": "degraded",
        "failed": "failed",
        "adminlocked": "failed",
        "adminlocked_suspended": "failed",
    }.get(status.lower(), "unknown")
