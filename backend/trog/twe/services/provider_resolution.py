from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from ..db import fetch_one
from .adapters import adapter_for
from .provider_contracts import (
    BoundSecretAccessor,
    ProviderConnectionRecord,
    ProviderContext,
    ProviderResourceRecord,
    ProviderSecretEnvelope,
    TimeoutPolicy,
)
from .provider_registry import build_provider_registry


@dataclass(frozen=True)
class ResolvedGameServerProvider:
    mode: str
    management_adapter: str
    context: ProviderContext | None = None


def read_game_server_health(resolution: ResolvedGameServerProvider, config) -> dict | None:
    if resolution.mode == "provider":
        reader = build_provider_registry(config).status_reader(
            resolution.context.connection.provider_key
        )
        return reader.read_status(resolution.context).as_health_payload()
    adapter = adapter_for(resolution.management_adapter)
    return adapter.health(config) if adapter else None


def read_game_server_players(resolution: ResolvedGameServerProvider, config) -> dict:
    if resolution.mode == "provider":
        reader = build_provider_registry(config).player_reader(
            resolution.context.connection.provider_key
        )
        return reader.read_players(resolution.context)
    from services.rcon import list_players

    return list_players()


def read_game_server_mods(resolution: ResolvedGameServerProvider, config) -> list[dict[str, str]]:
    if resolution.mode == "provider":
        reader = build_provider_registry(config).mod_reader(
            resolution.context.connection.provider_key
        )
        return reader.read_mods(resolution.context)
    adapter = adapter_for(resolution.management_adapter)
    if not adapter or not hasattr(adapter, "installed_mods"):
        raise LookupError("The connected server does not expose an installed mod list.")
    return adapter.installed_mods(config)


def resolve_game_server_provider(
    conn,
    game_server_id: str,
    *,
    correlation_id: str | None = None,
    timeout_policy: TimeoutPolicy | None = None,
) -> ResolvedGameServerProvider | None:
    row = fetch_one(
        conn,
        """
        SELECT gs.id::text AS game_server_id,
               gs.management_adapter,
               gs.provider_resource_id::text,
               pr.provider_connection_id::text,
               pr.resource_type,
               pr.external_resource_id,
               pr.display_name AS resource_display_name,
               pr.provider_game_key,
               pr.normalized_status,
               pr.provider_status,
               pr.metadata,
               pc.id::text AS connection_id,
               pc.community_id::text AS connection_community_id,
               pc.provider_key,
               pc.display_name AS connection_display_name,
               pc.auth_strategy,
               pc.external_account_id,
               pc.status AS connection_status,
               pcs.storage_kind,
               pcs.secret_reference,
               pcs.encrypted_payload,
               pcs.encryption_nonce,
               pcs.key_version,
               pcs.expires_at
        FROM game_servers gs
        LEFT JOIN provider_resources pr ON pr.id = gs.provider_resource_id
        LEFT JOIN provider_connections pc ON pc.id = pr.provider_connection_id
        LEFT JOIN provider_connection_secrets pcs ON pcs.provider_connection_id = pc.id
        WHERE gs.id = %s
        """,
        (game_server_id,),
    )
    if not row:
        return None
    if not row["provider_resource_id"]:
        return ResolvedGameServerProvider(
            mode="legacy",
            management_adapter=row["management_adapter"],
        )

    envelope = None
    if row["storage_kind"]:
        envelope = ProviderSecretEnvelope(
            storage_kind=row["storage_kind"],
            secret_reference=row["secret_reference"],
            encrypted_payload=row["encrypted_payload"],
            encryption_nonce=row["encryption_nonce"],
            key_version=row["key_version"],
            expires_at=row["expires_at"],
        )
    context = ProviderContext(
        connection=ProviderConnectionRecord(
            id=row["connection_id"],
            community_id=row["connection_community_id"],
            provider_key=row["provider_key"],
            display_name=row["connection_display_name"],
            auth_strategy=row["auth_strategy"],
            external_account_id=row["external_account_id"],
            status=row["connection_status"],
        ),
        resource=ProviderResourceRecord(
            id=row["provider_resource_id"],
            provider_connection_id=row["provider_connection_id"],
            resource_type=row["resource_type"],
            external_resource_id=row["external_resource_id"],
            display_name=row["resource_display_name"],
            provider_game_key=row["provider_game_key"],
            normalized_status=row["normalized_status"],
            provider_status=row["provider_status"],
            metadata=dict(row["metadata"] or {}),
        ),
        secret_accessor=BoundSecretAccessor(envelope),
        correlation_id=correlation_id or str(uuid4()),
        timeout_policy=timeout_policy or TimeoutPolicy(),
    )
    return ResolvedGameServerProvider(
        mode="provider",
        management_adapter=row["management_adapter"],
        context=context,
    )
