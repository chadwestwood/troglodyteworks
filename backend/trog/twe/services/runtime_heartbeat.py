from __future__ import annotations

import json
from datetime import datetime, timezone

from ..db import execute


ALLOWED_COMPONENTS = {"trog_worker"}
ALLOWED_STATUSES = {"ready", "connecting", "degraded"}
ALLOWED_DETAIL_KEYS = {"guild_count"}
STALE_AFTER_SECONDS = 120


def record_runtime_heartbeat(conn, component: str, status: str, details: dict | None = None):
    if component not in ALLOWED_COMPONENTS or status not in ALLOWED_STATUSES:
        raise ValueError("Unsupported runtime heartbeat value.")
    safe_details = {
        key: value
        for key, value in (details or {}).items()
        if key in ALLOWED_DETAIL_KEYS and isinstance(value, int) and not isinstance(value, bool) and value >= 0
    }
    execute(
        conn,
        """
        INSERT INTO runtime_heartbeats (component, status, details, checked_at, updated_at)
        VALUES (%s, %s, %s::jsonb, now(), now())
        ON CONFLICT (component) DO UPDATE
        SET status = EXCLUDED.status,
            details = EXCLUDED.details,
            checked_at = EXCLUDED.checked_at,
            updated_at = now()
        """,
        (component, status, json.dumps(safe_details, separators=(",", ":"))),
    )


def runtime_heartbeat_response(rows, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    components = []
    for row in rows:
        checked_at = row["checked_at"]
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((now - checked_at).total_seconds()))
        status = "stale" if age_seconds > STALE_AFTER_SECONDS else row["status"]
        components.append({
            "component": row["component"],
            "status": status,
            "reported_status": row["status"],
            "checked_at": checked_at,
            "age_seconds": age_seconds,
            "details": {
                key: value
                for key, value in dict(row.get("details") or {}).items()
                if key in ALLOWED_DETAIL_KEYS
            },
        })
    return components
