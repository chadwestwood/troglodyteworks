"""Durable, provider-neutral configuration snapshots for individual Worlds."""

import json
import re
import uuid

from ..db import execute, fetch_one
from .provider_contracts import ProviderSetting, ProviderSettingsSnapshot


_SENSITIVE_PATH_PARTS = (
    "password",
    "secret",
    "token",
    "apikey",
    "credential",
    "webhook",
)


def sanitize_world_settings(settings):
    """Remove credentials before provider configuration enters durable storage."""
    safe = []
    for setting in settings:
        compact_path = re.sub(r"[^a-z0-9]", "", str(setting.path).lower())
        if any(part in compact_path for part in _SENSITIVE_PATH_PARTS):
            continue
        safe.append(ProviderSetting(path=str(setting.path), value=str(setting.value)))
    return tuple(safe)


def load_world_configuration_snapshot(conn, game_instance_id):
    row = fetch_one(
        conn,
        """
        SELECT settings, checked_at
        FROM world_configuration_snapshots
        WHERE game_instance_id = %s
        ORDER BY checked_at DESC, created_at DESC
        LIMIT 1
        """,
        (game_instance_id,),
    )
    if not row:
        return None
    raw_settings = row["settings"]
    if isinstance(raw_settings, str):
        raw_settings = json.loads(raw_settings)
    settings = sanitize_world_settings(
        ProviderSetting(path=item["path"], value=item["value"])
        for item in raw_settings
        if isinstance(item, dict) and "path" in item and "value" in item
    )
    checked_at = row["checked_at"]
    if hasattr(checked_at, "isoformat"):
        checked_at = checked_at.isoformat()
    return ProviderSettingsSnapshot(settings=settings, checked_at=str(checked_at))


def store_world_configuration_snapshot(
    conn,
    *,
    game_instance_id,
    provider_key,
    source_kind,
    snapshot,
):
    safe_settings = sanitize_world_settings(snapshot.settings)
    payload = json.dumps(
        [{"path": item.path, "value": item.value} for item in safe_settings],
        separators=(",", ":"),
    )
    execute(
        conn,
        """
        INSERT INTO world_configuration_snapshots (
            id, game_instance_id, provider_key, source_kind, settings, checked_at
        ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
        """,
        (
            str(uuid.uuid4()),
            game_instance_id,
            provider_key,
            source_kind,
            payload,
            snapshot.checked_at,
        ),
    )
    return ProviderSettingsSnapshot(settings=safe_settings, checked_at=snapshot.checked_at)
