from __future__ import annotations

from . import local_asa
from .provider_contracts import (
    ConnectionDescription,
    ProviderContext,
    ProviderStatus,
    ProviderStatusCheck,
)


STATUS_MAP = {
    "ready": "online",
    "offline": "offline",
    "degraded": "degraded",
    "failed": "failed",
    "unknown": "unknown",
}


class SelfHostedProvider:
    def __init__(self, config):
        self._config = config

    def describe_connection(self) -> ConnectionDescription:
        return ConnectionDescription(
            provider_key="self_hosted",
            display_name="Self-hosted",
            auth_strategy="configuration",
        )

    def read_status(self, context: ProviderContext) -> ProviderStatus:
        if context.connection.provider_key != "self_hosted":
            raise ValueError("Self-hosted adapter received the wrong Provider Connection.")
        health = local_asa.health(self._config)
        overall_status = str(health.get("overall_status") or "unknown")
        checks = tuple(
            ProviderStatusCheck(
                name=str(check.get("name") or "unknown"),
                status=str(check.get("status") or "unknown"),
                message=str(check.get("message") or ""),
            )
            for check in health.get("checks", [])
        )
        return ProviderStatus(
            normalized_status=STATUS_MAP.get(overall_status, "unknown"),
            provider_status=overall_status,
            checked_at=str(health.get("checked_at") or ""),
            checks=checks,
        )
