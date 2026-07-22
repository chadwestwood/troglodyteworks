from __future__ import annotations

from datetime import datetime, timezone
from . import local_asa
from .provider_contracts import (
    ConnectionDescription,
    ProviderContext,
    ProviderStatus,
    ProviderStatusCheck,
)


STATUS_MAP = {
    "ready": "online",
    "online": "online",
    "offline": "offline",
    "starting": "starting",
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
        # Preserve the original on-box adapter for legacy records. Newly paired
        # customer hosts report normalized state through resource metadata.
        if context.connection.external_account_id == "local-installation":
            health = local_asa.health(self._config)
            return ProviderStatus(
                normalized_status=STATUS_MAP.get(str(health.get("overall_status") or "unknown"), "unknown"),
                provider_status=str(health.get("overall_status") or "unknown"),
                checked_at=str(health.get("checked_at") or ""),
                checks=tuple(ProviderStatusCheck(
                    name=str(check.get("name") or "unknown"),
                    status=str(check.get("status") or "unknown"),
                    message=str(check.get("message") or ""),
                ) for check in health.get("checks", [])),
            )
        overall_status = context.resource.normalized_status or "unknown"
        provider_status = "ready" if overall_status == "online" else overall_status
        checks = (ProviderStatusCheck(
            name="host_agent", status="passed" if overall_status == "online" else overall_status,
            message="Reported by the paired Trog Host Agent.",
        ),)
        return ProviderStatus(
            normalized_status=STATUS_MAP.get(overall_status, "unknown"),
            provider_status=provider_status,
            checked_at=datetime.now(timezone.utc).isoformat(),
            checks=checks,
        )

    def read_players(self, context: ProviderContext) -> dict:
        players = context.resource.metadata.get("players") or []
        if not isinstance(players, list):
            players = []
        names = [str(name)[:100] for name in players if isinstance(name, str)][:200]
        return {"players": names}

    def read_mods(self, context: ProviderContext) -> list[dict[str, str]]:
        mods = context.resource.metadata.get("mods") or []
        if not isinstance(mods, list):
            return []
        return [{"id": str(mod.get("id") or ""), "name": str(mod.get("name") or "Unknown mod")[:150]}
                for mod in mods[:500] if isinstance(mod, dict)]
