from __future__ import annotations

from datetime import datetime, timezone

from ..db import execute, fetch_one
from .hosting import InstanceSpec
from .hosting_providers import provider_for


def map_provider_status(provider_status: str) -> str:
    if provider_status == "ready":
        return "online"
    if provider_status == "failed":
        return "failed"
    return "starting"


def begin_provisioning(conn, config, provider_name: str, instance_row, operation_id: str):
    started = datetime.now(timezone.utc)
    execute(
        conn,
        """
        UPDATE server_operations
        SET status = 'executing', current_stage = 'provider_create', started_at = COALESCE(started_at, %s)
        WHERE id = %s
        """,
        (started, operation_id),
    )
    spec = InstanceSpec(
        instance_id=instance_row["id"],
        community_id=instance_row["community_id"],
        game_key=instance_row["game_key"],
        map_key=instance_row["map_key"],
        name=instance_row["name"],
    )
    try:
        provider = provider_for(provider_name, config)
        state = provider.create_instance(spec)
        mapped_status = map_provider_status(state.provider_status)
        execute(
            conn,
            """
            UPDATE game_instances
            SET hosting_provider = %s,
                provider_instance_id = %s,
                provider_state = %s,
                status = %s,
                provisioning_error = NULL,
                updated_at = now()
            WHERE id = %s
            """,
            (provider_name, state.provider_instance_id, state.provider_status, mapped_status, instance_row["id"]),
        )
        if mapped_status == "online":
            complete_operation(conn, operation_id, "completed", "Instance is ready.")
        elif mapped_status == "failed":
            complete_operation(conn, operation_id, "failed", state.detail or "Provider reported a failed provisioning status.")
        else:
            execute(
                conn,
                """
                UPDATE server_operations
                SET current_stage = 'provider_install', result_message = 'Provisioning started.'
                WHERE id = %s
                """,
                (operation_id,),
            )
    except Exception as exc:  # pragma: no cover - integration path
        message = str(exc)[:400]
        execute(
            conn,
            """
            UPDATE game_instances
            SET status = 'failed',
                provisioning_error = %s,
                updated_at = now()
            WHERE id = %s
            """,
            (message, instance_row["id"]),
        )
        complete_operation(conn, operation_id, "failed", message)


def reconcile_instance(conn, config, instance_id: str):
    row = fetch_one(
        conn,
        """
        SELECT gi.id::text, gi.hosting_provider, gi.provider_instance_id, gi.provider_state,
               gi.status, so.id::text AS operation_id, so.status AS operation_status
        FROM game_instances gi
        LEFT JOIN LATERAL (
            SELECT id, status
            FROM server_operations
            WHERE game_instance_id = gi.id AND capability = 'instance.provision'
            ORDER BY requested_at DESC
            LIMIT 1
        ) so ON true
        WHERE gi.id = %s
        """,
        (instance_id,),
    )
    if not row or not row["hosting_provider"] or not row["provider_instance_id"]:
        return
    if row["status"] in {"online", "failed"} and row["operation_status"] in {"completed", "failed", None}:
        return

    try:
        provider = provider_for(row["hosting_provider"], config)
        state = provider.get_instance_status(row["provider_instance_id"])
    except Exception as exc:  # pragma: no cover - integration path
        if row["operation_id"] and row["operation_status"] not in {"completed", "failed", "cancelled"}:
            complete_operation(conn, row["operation_id"], "failed", str(exc)[:400])
        execute(
            conn,
            """
            UPDATE game_instances
            SET status = 'failed', provisioning_error = %s, updated_at = now()
            WHERE id = %s
            """,
            (str(exc)[:400], instance_id),
        )
        return

    mapped_status = map_provider_status(state.provider_status)
    execute(
        conn,
        """
        UPDATE game_instances
        SET provider_state = %s,
            status = %s,
            provisioning_error = CASE WHEN %s = 'failed' THEN COALESCE(provisioning_error, %s) ELSE provisioning_error END,
            updated_at = now()
        WHERE id = %s
        """,
        (state.provider_status, mapped_status, mapped_status, state.detail or "Provider reported failure.", instance_id),
    )
    if not row["operation_id"] or row["operation_status"] in {"completed", "failed", "cancelled"}:
        return
    if mapped_status == "online":
        complete_operation(conn, row["operation_id"], "completed", "Instance is ready.")
    elif mapped_status == "failed":
        complete_operation(conn, row["operation_id"], "failed", state.detail or "Provisioning failed in hosting provider.")
    else:
        execute(
            conn,
            """
            UPDATE server_operations
            SET status = 'executing', current_stage = 'provider_install', result_message = 'Provisioning in progress.'
            WHERE id = %s
            """,
            (row["operation_id"],),
        )


def complete_operation(conn, operation_id: str, status: str, message: str):
    execute(
        conn,
        """
        UPDATE server_operations
        SET status = %s,
            current_stage = %s,
            completed_at = now(),
            result_message = %s
        WHERE id = %s
        """,
        (status, status, message, operation_id),
    )
