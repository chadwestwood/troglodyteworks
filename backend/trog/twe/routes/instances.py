from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from .auth import validate_image_value
from ..authorization import can_request_capability, instance_access
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..serializers import operation_summary, operation_with_requester
from ..services.adapters import adapter_for
from ..services.instance_provisioning import reconcile_instance
from ..services.nitrado_provider import NitradoProviderError
from ..services.provider_resolution import (
    read_game_server_health,
    read_game_server_mods,
    read_game_server_players,
    resolve_game_server_provider,
)

instances_bp = Blueprint("twe_instances", __name__)

ACTIVE_STATUSES = ("requested", "queued", "executing", "verifying")
VALID_OPERATION_STATUSES = ACTIVE_STATUSES + ("completed", "failed", "cancelled")


@instances_bp.get("/instances/<instance_id>")
@require_user
def get_instance(instance_id):
    with current_app.config["TWE_DB"].connect() as conn:
        row = instance_access(conn, g.current_user["id"], instance_id)
        if not row:
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        # Reconciliation may contact a provider and mutate Instance state. The
        # tenant boundary must therefore be established before it is attempted.
        reconcile_instance(conn, current_app.config["TWE_CONFIG"], instance_id)
        instance = fetch_one(
            conn,
            """
            SELECT hosting_provider, provider_instance_id, provider_state, provisioning_error, image_url
            FROM game_instances
            WHERE id = %s
            """,
            (instance_id,),
        )
    return jsonify(
        {
            "instance": {
                "id": row["instance_id"],
                "game_server_id": row["game_server_id"],
                "game_server_name": row["game_server_name"],
                "game_server_slug": row["game_server_slug"],
                "game_type": row["game_type"],
                "community_id": row["community_id"],
                "community_name": row["community_name"],
                "name": row["instance_name"],
                "slug": row["instance_slug"],
                "instance_type": row["instance_type"],
                "game_identifier": row["game_identifier"],
                "status": row["instance_status"],
                "hosting_provider": instance["hosting_provider"],
                "provider_instance_id": instance["provider_instance_id"],
                "provider_state": instance["provider_state"],
                "provisioning_error": instance["provisioning_error"],
                "image_url": instance.get("image_url"),
                "viewer_role": row["role"],
            }
        }
    )


@instances_bp.patch("/instances/<instance_id>/identity")
@require_user
def update_instance_identity(instance_id):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    image_url = validate_image_value(payload.get("image_url"))
    if not name or len(name) > 120:
        return api_error("VALIDATION_ERROR", "Server name must be between 1 and 120 characters.", 400)
    if image_url is False:
        return api_error("VALIDATION_ERROR", "Use a PNG, JPEG, or WebP image under 450 KB.", 400)
    with current_app.config["TWE_DB"].connect() as conn:
        access = instance_access(conn, g.current_user["id"], instance_id)
        if not access or access["role"] not in {"owner", "admin"}:
            return api_error("FORBIDDEN", "Only Community owners and admins can change this server identity.", 403)
        duplicate = fetch_one(conn, """
            SELECT gi.id FROM game_instances gi
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE gs.community_id = %s AND lower(gi.name) = lower(%s) AND gi.id <> %s
        """, (access["community_id"], name, instance_id))
        if duplicate:
            return api_error("NAME_ALREADY_USED", "Another server in this Community already uses that name.", 409)
        instance = fetch_one(conn, """
            UPDATE game_instances SET name = %s, image_url = %s, updated_at = now()
            WHERE id = %s RETURNING id::text, name, slug, status, image_url
        """, (name, image_url, instance_id))
    return jsonify({"instance": instance})


@instances_bp.get("/instances/<instance_id>/health")
@require_user
def get_health(instance_id):
    with current_app.config["TWE_DB"].connect() as conn:
        row = instance_access(conn, g.current_user["id"], instance_id)
        if not row:
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        resolution = resolve_game_server_provider(conn, row["game_server_id"])
    try:
        health = read_game_server_health(resolution, current_app.config["TWE_CONFIG"])
    except NitradoProviderError as error:
        # Provider exceptions have fixed, secret-free messages and status codes.
        # Preserve that contract instead of masking an expected outage or
        # reauthorization condition as a generic application failure.
        return api_error(error.code, str(error), error.http_status)
    if health is None:
        return jsonify(
            {
                "health": {
                    "overall_status": "unknown",
                    "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "checks": [
                        {
                            "name": "management_adapter",
                            "status": "not_configured",
                            "message": "Management Adapter is not configured.",
                        }
                    ],
                }
            }
        )
    return jsonify({"health": health})


@instances_bp.get("/instances/<instance_id>/overview")
@require_user
def get_instance_overview(instance_id):
    """Return the small, member-facing snapshot used by an Instance home."""
    with current_app.config["TWE_DB"].connect() as conn:
        access = instance_access(conn, g.current_user["id"], instance_id)
        if not access:
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        resolution = resolve_game_server_provider(conn, access["game_server_id"])

    health = None
    players = None
    mods = None
    try:
        health = read_game_server_health(resolution, current_app.config["TWE_CONFIG"])
    except Exception:
        # An unavailable provider should not make the whole member home fail.
        pass
    try:
        player_result = read_game_server_players(resolution, current_app.config["TWE_CONFIG"])
        players = {"count": int(player_result.get("count", len(player_result.get("players") or [])))}
    except Exception:
        pass
    try:
        mods = read_game_server_mods(resolution, current_app.config["TWE_CONFIG"])
    except Exception:
        pass

    return jsonify(
        {
            "overview": {
                "health": health,
                "players": players,
                "mods": mods,
            }
        }
    )


@instances_bp.get("/instances/<instance_id>/capabilities")
@require_user
def get_capabilities(instance_id):
    with current_app.config["TWE_DB"].connect() as conn:
        row = instance_access(conn, g.current_user["id"], instance_id)
        if not row:
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        adapter = adapter_for(row["management_adapter"])
        capabilities = adapter.capabilities() if adapter else []
        for capability in capabilities:
            if not can_request_capability(row, capability["key"], conn):
                capability["available"] = False
                capability["unavailable_reason"] = "Your Community role cannot request this Capability."
    return jsonify({"capabilities": capabilities})


@instances_bp.post("/instances/<instance_id>/server-operations")
@require_user
def create_operation(instance_id):
    payload = request.get_json(silent=True) or {}
    capability_key = payload.get("capability")
    if not isinstance(capability_key, str):
        return api_error("VALIDATION_ERROR", "Capability is required.", 400)

    resolution = None
    with current_app.config["TWE_DB"].connect() as conn:
        access = instance_access(conn, g.current_user["id"], instance_id)
        if not access:
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        adapter = adapter_for(access["management_adapter"])
        capability = adapter.capability_for(capability_key) if adapter else None
        if not capability:
            return api_error("VALIDATION_ERROR", "Capability is not defined for this Instance.", 400)
        if not can_request_capability(access, capability_key, conn):
            return api_error("FORBIDDEN", "You do not have permission to perform this operation.", 403)
        if capability.get("requires_confirmation") and payload.get("confirmed") is not True:
            return api_error("CONFIRMATION_REQUIRED", "This operation requires confirmation.", 400)
        if not capability.get("available"):
            return api_error(
                "CAPABILITY_UNAVAILABLE",
                capability.get("unavailable_reason", "This Capability is not available."),
                409,
            )

        active = fetch_one(
            conn,
            """
            SELECT id::text
            FROM server_operations
            WHERE game_instance_id = %s AND status = ANY(%s)
            LIMIT 1
            """,
            (instance_id, list(ACTIVE_STATUSES)),
        )
        if active:
            return api_error(
                "OPERATION_ALREADY_RUNNING",
                "A conflicting Server Operation is already active for this Instance.",
                409,
            )

        row = fetch_one(
            conn,
            """
            INSERT INTO server_operations (game_instance_id, requested_by, capability, status)
            VALUES (%s, %s, %s, 'requested')
            RETURNING id::text, game_instance_id::text, capability, status, current_stage,
                      requested_at, started_at, completed_at, result_message
            """,
            (instance_id, g.current_user["id"], capability_key),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
            VALUES (%s, %s, %s, 'server_operation', %s, jsonb_build_object('capability', %s::text))
            """,
            (g.current_user["id"], access["community_id"], "server_operation.created", row["id"], capability_key),
        )
        if capability_key == "instance.status":
            resolution = resolve_game_server_provider(conn, access["game_server_id"])

    if capability_key == "instance.status":
        try:
            health = read_game_server_health(resolution, current_app.config["TWE_CONFIG"])
        except Exception:
            health = None
        if health is None:
            health = {
                "overall_status": "unknown",
                "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "checks": [
                    {
                        "name": "management_adapter",
                        "status": "unknown",
                        "message": "The status service could not complete the health check.",
                    }
                ],
            }
        with current_app.config["TWE_DB"].connect() as conn:
            _complete_status_operation(conn, row["id"], health)
            row = _operation_by_id(conn, row["id"])

    return jsonify({"server_operation": operation_summary(row)}), 202


@instances_bp.get("/instances/<instance_id>/server-operations")
@require_user
def list_operations(instance_id):
    status = request.args.get("status")
    capability = request.args.get("capability")
    try:
        limit = min(int(request.args.get("limit", "20")), 50)
    except ValueError:
        return api_error("VALIDATION_ERROR", "Limit must be a number.", 400)
    if status and status not in VALID_OPERATION_STATUSES:
        return api_error("VALIDATION_ERROR", "Unsupported status filter.", 400)

    query = """
        SELECT so.id::text, so.game_instance_id::text, so.requested_by::text, so.capability,
               so.status, so.current_stage, so.requested_at, so.started_at, so.completed_at,
               so.result_message, users.display_name AS requested_by_display_name
        FROM server_operations so
        JOIN users ON users.id = so.requested_by
        WHERE so.game_instance_id = %s
    """
    params = [instance_id]
    if status:
        query += " AND so.status = %s"
        params.append(status)
    if capability:
        query += " AND so.capability = %s"
        params.append(capability)
    query += " ORDER BY so.requested_at DESC LIMIT %s"
    params.append(limit)

    with current_app.config["TWE_DB"].connect() as conn:
        if not instance_access(conn, g.current_user["id"], instance_id):
            return api_error("NOT_FOUND", "Game Instance was not found.", 404)
        rows = fetch_all(conn, query, tuple(params))
    return jsonify({"server_operations": [operation_with_requester(row) for row in rows]})


def _complete_status_operation(conn, operation_id: str, health: dict):
    started = datetime.now(timezone.utc)
    execute(
        conn,
        """
        UPDATE server_operations
        SET status = 'executing', current_stage = 'health_check', started_at = %s
        WHERE id = %s
        """,
        (started, operation_id),
    )
    final_status = "completed" if health["overall_status"] == "ready" else "failed"
    message = "Instance health is ready." if final_status == "completed" else "Instance health is not ready."
    order = 1
    for check in health["checks"]:
        check_status = "passed" if check["status"] == "passed" else "failed"
        if check["status"] in {"not_configured", "unknown", "pending"}:
            check_status = "skipped"
        execute(
            conn,
            """
            INSERT INTO server_operation_checks
                (server_operation_id, name, status, started_at, completed_at, result_message, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (operation_id, check["name"], check_status, started, datetime.now(timezone.utc), check["message"], order),
        )
        order += 1
    execute(
        conn,
        """
        UPDATE server_operations
        SET status = %s, current_stage = %s, completed_at = %s, result_message = %s
        WHERE id = %s
        """,
        (final_status, final_status, datetime.now(timezone.utc), message, operation_id),
    )


def _operation_by_id(conn, operation_id: str):
    return fetch_one(
        conn,
        """
        SELECT id::text, game_instance_id::text, requested_by::text, capability, status,
               current_stage, requested_at, started_at, completed_at, result_message
        FROM server_operations
        WHERE id = %s
        """,
        (operation_id,),
    )
