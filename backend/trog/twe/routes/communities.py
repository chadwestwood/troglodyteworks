from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..services.game_catalog import resolve_catalog_selection
from ..services.instance_provisioning import begin_provisioning

communities_bp = Blueprint("twe_communities", __name__)


@communities_bp.get("/communities")
@require_user
def list_communities():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT c.id::text,
                   c.name,
                   c.slug,
                   cm.role,
                   (SELECT count(*)::int FROM community_memberships cm2 WHERE cm2.community_id = c.id) AS member_count,
                   (SELECT count(*)::int FROM game_servers gs WHERE gs.community_id = c.id) AS connected_services,
                   (SELECT count(*)::int FROM game_servers gs
                    WHERE gs.community_id = c.id AND gs.status IN ('online', 'degraded', 'starting')) AS healthy_services,
                   (
                       (SELECT count(*)::int FROM game_servers gs WHERE gs.community_id = c.id AND gs.status IN ('offline', 'failed'))
                       +
                       (SELECT count(*)::int
                        FROM server_operations so
                        JOIN game_instances gi ON gi.id = so.game_instance_id
                        JOIN game_servers gs ON gs.id = gi.game_server_id
                        WHERE gs.community_id = c.id
                          AND so.status = 'failed'
                          AND so.requested_at >= now() - interval '7 days')
                   ) AS attention_count
            FROM communities c
            JOIN community_memberships cm ON cm.community_id = c.id
            WHERE cm.user_id = %s
            ORDER BY c.name
            """,
            (g.current_user["id"],),
        )
    return jsonify({"communities": rows})


@communities_bp.get("/communities/<community_id>")
@require_user
def get_community(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        community = fetch_one(
            conn,
            "SELECT id::text, name, slug, description FROM communities WHERE id = %s",
            (community_id,),
        )
        if not community:
            return api_error("NOT_FOUND", "Community was not found.", 404)
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership:
            return api_error("FORBIDDEN", "You do not have access to this Community.", 403)

    community["current_user_role"] = membership["role"]
    return jsonify({"community": community})


@communities_bp.get("/communities/<community_id>/game-servers")
@require_user
def list_game_servers(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not membership_for_community(conn, g.current_user["id"], community_id):
            return api_error("FORBIDDEN", "You do not have access to this Community.", 403)
        rows = fetch_all(
            conn,
            """
            SELECT id::text, community_id::text, name, slug, game_type, status
            FROM game_servers
            WHERE community_id = %s
            ORDER BY name
            """,
            (community_id,),
        )
    return jsonify({"game_servers": rows})


@communities_bp.get("/communities/<community_id>/operations-home")
@require_user
def operations_home(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        community = fetch_one(
            conn,
            """
            SELECT c.id::text, c.name, c.slug, c.description, cm.role AS viewer_role
            FROM communities c
            JOIN community_memberships cm ON cm.community_id = c.id
            WHERE c.id = %s AND cm.user_id = %s
            """,
            (community_id, g.current_user["id"]),
        )
        if not community:
            return api_error("FORBIDDEN", "You do not have access to this Community.", 403)

        summary_row = fetch_one(
            conn,
            """
            SELECT
                (SELECT count(*)::int FROM community_memberships WHERE community_id = %s) AS member_count,
                (SELECT count(*)::int FROM game_servers WHERE community_id = %s) AS connected_services,
                (SELECT count(*)::int FROM game_servers WHERE community_id = %s AND status IN ('online', 'degraded', 'starting')) AS healthy_services,
                (SELECT count(*)::int FROM game_servers WHERE community_id = %s AND status IN ('offline', 'failed')) AS disconnected_services,
                (SELECT count(*)::int
                 FROM server_operations so
                 JOIN game_instances gi ON gi.id = so.game_instance_id
                 JOIN game_servers gs ON gs.id = gi.game_server_id
                 WHERE gs.community_id = %s
                   AND so.status = 'failed'
                   AND so.requested_at >= now() - interval '7 days') AS failed_operations
            """,
            (community_id, community_id, community_id, community_id, community_id),
        )

        member_rows = fetch_all(
            conn,
            """
            SELECT role, count(*)::int AS count
            FROM community_memberships
            WHERE community_id = %s
            GROUP BY role
            """,
            (community_id,),
        )
        new_members = fetch_one(
            conn,
            """
            SELECT count(*)::int AS count
            FROM community_memberships
            WHERE community_id = %s
              AND joined_at >= now() - interval '7 days'
            """,
            (community_id,),
        )

        connected_services = fetch_all(
            conn,
            """
            SELECT gs.id::text,
                   gs.name,
                   gs.slug,
                   gs.game_type,
                   gs.status,
                   gs.management_adapter,
                   count(gi.id)::int AS instance_count,
                   count(*) FILTER (WHERE gi.status = 'online')::int AS online_instances,
                   min(gi.name) FILTER (WHERE gi.status IN ('online', 'starting', 'degraded')) AS active_world,
                   min(gi.name) AS any_world,
                   op.capability AS latest_operation_capability,
                   op.status AS latest_operation_status,
                   op.requested_at AS latest_operation_requested_at
            FROM game_servers gs
            LEFT JOIN game_instances gi ON gi.game_server_id = gs.id
            LEFT JOIN LATERAL (
                SELECT so.capability, so.status, so.requested_at
                FROM server_operations so
                JOIN game_instances gi2 ON gi2.id = so.game_instance_id
                WHERE gi2.game_server_id = gs.id
                ORDER BY so.requested_at DESC
                LIMIT 1
            ) op ON true
            WHERE gs.community_id = %s
            GROUP BY gs.id, op.capability, op.status, op.requested_at
            ORDER BY gs.name
            """,
            (community_id,),
        )

        failed_operations = fetch_all(
            conn,
            """
            SELECT so.id::text,
                   so.capability,
                   so.result_message,
                   so.completed_at,
                   gi.name AS instance_name,
                   gs.name AS service_name
            FROM server_operations so
            JOIN game_instances gi ON gi.id = so.game_instance_id
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE gs.community_id = %s
              AND so.status = 'failed'
            ORDER BY coalesce(so.completed_at, so.requested_at) DESC
            LIMIT 6
            """,
            (community_id,),
        )

        upcoming_operations = fetch_all(
            conn,
            """
            SELECT so.id::text,
                   so.capability,
                   so.status,
                   so.requested_at,
                   gi.name AS instance_name,
                   gs.name AS service_name
            FROM server_operations so
            JOIN game_instances gi ON gi.id = so.game_instance_id
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE gs.community_id = %s
              AND so.status = ANY(%s)
            ORDER BY so.requested_at ASC
            LIMIT 6
            """,
            (community_id, ["requested", "queued", "executing", "verifying"]),
        )

        activity_operations = fetch_all(
            conn,
            """
            SELECT so.id::text,
                   so.capability,
                   so.status,
                   so.requested_at,
                   users.display_name AS actor_name,
                   gi.name AS instance_name
            FROM server_operations so
            JOIN game_instances gi ON gi.id = so.game_instance_id
            JOIN game_servers gs ON gs.id = gi.game_server_id
            JOIN users ON users.id = so.requested_by
            WHERE gs.community_id = %s
            ORDER BY so.requested_at DESC
            LIMIT 8
            """,
            (community_id,),
        )

        recent_joins = fetch_all(
            conn,
            """
            SELECT u.display_name, cm.joined_at
            FROM community_memberships cm
            JOIN users u ON u.id = cm.user_id
            WHERE cm.community_id = %s
            ORDER BY cm.joined_at DESC
            LIMIT 5
            """,
            (community_id,),
        )

        pending_request_count = 0
        if community["viewer_role"] in {"owner", "admin", "moderator"}:
            pending = fetch_one(
                conn,
                """
                SELECT count(*)::int AS count
                FROM community_invitation_redemptions cir
                JOIN community_invitations ci ON ci.id = cir.invitation_id
                WHERE ci.community_id = %s
                  AND cir.status = 'pending_approval'
                """,
                (community_id,),
            )
            pending_request_count = pending["count"] if pending else 0

    attention_items = []
    for service in connected_services:
        if service["status"] in {"offline", "failed"}:
            attention_items.append(
                {
                    "type": "service_connection",
                    "title": f"{service['name']} needs attention",
                    "service": service["name"],
                    "status": _humanize_status(service["status"]),
                    "next_action": "Review the connected service details.",
                    "href": f"/communities/{community['slug']}/game-servers/{service['slug']}/",
                }
            )
    for operation in failed_operations:
        attention_items.append(
            {
                "type": "failed_operation",
                "title": f"{_operation_title(operation['capability'])} failed",
                "service": operation["service_name"],
                "instance": operation["instance_name"],
                "status": "Failed",
                "next_action": operation["result_message"] or "Review operation details and retry when ready.",
                "href": f"/server-operations/?id={operation['id']}",
            }
        )
    if pending_request_count:
        attention_items.append(
            {
                "type": "pending_membership",
                "title": "Membership requests need review",
                "service": community["name"],
                "status": f"{pending_request_count} pending",
                "next_action": "Review and approve or deny pending requests.",
                "href": f"/communities/{community['slug']}/invitations/",
            }
        )

    upcoming_items = [
        {
            "type": "scheduled_change",
            "title": _operation_title(item["capability"]),
            "service": item["service_name"],
            "instance": item["instance_name"],
            "status": _humanize_status(item["status"]),
            "scheduled_for": _iso(item["requested_at"]),
            "href": f"/server-operations/?id={item['id']}",
        }
        for item in upcoming_operations
    ]

    activity_items = [
        {
            "type": "operation",
            "summary": f"{item['actor_name']} ran {_operation_title(item['capability']).lower()} on {item['instance_name']}.",
            "status": _humanize_status(item["status"]),
            "recorded_at": _iso(item["requested_at"]),
            "href": f"/server-operations/?id={item['id']}",
        }
        for item in activity_operations
    ]
    for join in recent_joins:
        activity_items.append(
            {
                "type": "membership",
                "summary": f"{join['display_name']} joined {community['name']}.",
                "status": "Member joined",
                "recorded_at": _iso(join["joined_at"]),
                "href": f"/communities/{community['slug']}/invitations/",
            }
        )

    member_counts = {row["role"]: row["count"] for row in member_rows}
    service_cards = [
        {
            "id": service["id"],
            "game": service["game_type"],
            "service_name": service["name"],
            "provider": _provider_label(service["management_adapter"]),
            "connection_status": _humanize_status(service["status"]),
            "service_health": _service_health_summary(service["status"]),
            "player_count": None,
            "world": service["active_world"] or service["any_world"],
            "scheduled_change": _operation_title(service["latest_operation_capability"]) if service["latest_operation_capability"] else None,
            "scheduled_change_status": _humanize_status(service["latest_operation_status"]) if service["latest_operation_status"] else None,
            "href": f"/communities/{community['slug']}/game-servers/{service['slug']}/",
        }
        for service in connected_services
    ]

    response = {
        "community": {
            "id": community["id"],
            "name": community["name"],
            "slug": community["slug"],
            "description": community["description"],
            "viewer_role": community["viewer_role"],
            "member_count": summary_row["member_count"],
        },
        "summary": {
            "players_online": None,
            "connected_services": summary_row["connected_services"],
            "healthy_services": summary_row["healthy_services"],
            "attention_count": len(attention_items),
        },
        "attention_items": attention_items,
        "upcoming_items": upcoming_items,
        "recent_activity": activity_items[:10],
        "member_summary": {
            "owners": member_counts.get("owner", 0),
            "administrators": member_counts.get("admin", 0),
            "moderators": member_counts.get("moderator", 0),
            "new_members": new_members["count"] if new_members else 0,
        },
        "connected_services": service_cards,
    }
    return jsonify(response)


@communities_bp.post("/communities/<community_id>/instances")
@require_user
def provision_instance(community_id):
    payload = request.get_json(silent=True) or {}
    game_key = str(payload.get("game_key") or "").strip()
    map_key = str(payload.get("map_key") or "").strip()
    idempotency_key = str(
        payload.get("idempotency_key")
        or request.headers.get("Idempotency-Key")
        or ""
    ).strip()
    if not game_key or not map_key:
        return api_error("VALIDATION_ERROR", "Game and map are required.", 400)
    if idempotency_key and len(idempotency_key) > 120:
        return api_error("VALIDATION_ERROR", "Idempotency key is too long.", 400)

    game, game_map = resolve_catalog_selection(game_key, map_key)
    if not game or not game_map:
        return api_error("VALIDATION_ERROR", "Unsupported game or map selection.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership or membership["role"] != "owner":
            return api_error("FORBIDDEN", "Only Community owners can provision new Instances.", 403)

        if idempotency_key:
            existing_request = fetch_one(
                conn,
                """
                SELECT ipr.id::text,
                       gi.id::text AS instance_id,
                      gi.id::text AS game_instance_id,
                       gi.game_server_id::text,
                       gi.name,
                       gi.slug,
                       gi.instance_type,
                       gi.game_identifier,
                       gi.status,
                       gi.hosting_provider,
                       gi.provider_instance_id,
                       gi.provider_state,
                       gi.provisioning_error,
                       so.id::text AS operation_id,
                       so.capability,
                       so.status AS operation_status,
                       so.current_stage,
                       so.requested_at,
                       so.started_at,
                       so.completed_at,
                       so.result_message
                FROM instance_provisioning_requests ipr
                JOIN game_instances gi ON gi.id = ipr.game_instance_id
                JOIN server_operations so ON so.id = ipr.server_operation_id
                WHERE ipr.community_id = %s
                  AND ipr.requested_by = %s
                  AND ipr.idempotency_key = %s
                """,
                (community_id, g.current_user["id"], idempotency_key),
            )
            if existing_request:
                return jsonify(
                    {
                        "instance": _instance_payload(existing_request),
                        "server_operation": _operation_payload(existing_request),
                        "idempotency_key": idempotency_key,
                    }
                ), 200

        existing_instance = fetch_one(
            conn,
            """
            SELECT gi.id::text
            FROM game_instances gi
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE gs.community_id = %s
              AND gs.game_type = %s
              AND gi.game_identifier = %s
              AND gi.status IN ('starting', 'degraded', 'online')
            LIMIT 1
            """,
            (community_id, game["name"], map_key),
        )
        if existing_instance:
            return api_error("INSTANCE_ALREADY_EXISTS", "A matching Instance already exists for this Community.", 409)

        server_slug = game_key.replace("_", "-")
        game_server = fetch_one(
            conn,
            """
            SELECT id::text, name, slug
            FROM game_servers
            WHERE community_id = %s AND slug = %s
            """,
            (community_id, server_slug),
        )
        if not game_server:
            game_server = fetch_one(
                conn,
                """
                INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter, status)
                VALUES (%s, %s, %s, %s, 'hosting_provider', 'starting')
                RETURNING id::text, name, slug
                """,
                (community_id, game["name"], server_slug, game["name"]),
            )

        instance = fetch_one(
            conn,
            """
            INSERT INTO game_instances
                (game_server_id, name, slug, instance_type, game_identifier, status, hosting_provider)
            VALUES (%s, %s, %s, 'ark_map', %s, 'starting', 'pterodactyl')
            RETURNING id::text, game_server_id::text, name, slug, instance_type, game_identifier,
                      status, hosting_provider, provider_instance_id, provider_state, provisioning_error
            """,
            (game_server["id"], game_map["name"], map_key, map_key),
        )
        operation = fetch_one(
            conn,
            """
            INSERT INTO server_operations (game_instance_id, requested_by, capability, status, current_stage)
            VALUES (%s, %s, 'instance.provision', 'requested', 'requested')
            RETURNING id::text, game_instance_id::text, capability, status, current_stage,
                      requested_at, started_at, completed_at, result_message
            """,
            (instance["id"], g.current_user["id"]),
        )
        request_key = idempotency_key or operation["id"]
        execute(
            conn,
            """
            INSERT INTO instance_provisioning_requests
                (community_id, requested_by, idempotency_key, game_key, map_key, game_instance_id, server_operation_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (community_id, g.current_user["id"], request_key, game_key, map_key, instance["id"], operation["id"]),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
            VALUES (%s, %s, %s, 'game_instance', %s,
                    jsonb_build_object('game_key', %s::text, 'map_key', %s::text, 'operation_id', %s::text))
            """,
            (g.current_user["id"], community_id, "instance.provision.requested", instance["id"], game_key, map_key, operation["id"]),
        )

        begin_provisioning(
            conn,
            current_app.config["TWE_CONFIG"],
            "pterodactyl",
            {
                "id": instance["id"],
                "community_id": community_id,
                "game_key": game_key,
                "map_key": map_key,
                "name": f"{game_map['name']} ({community_id[:8]})",
            },
            operation["id"],
        )
        refreshed_instance = fetch_one(
            conn,
            """
            SELECT id::text AS instance_id,
                   game_server_id::text,
                   name,
                   slug,
                   instance_type,
                   game_identifier,
                   status,
                   hosting_provider,
                   provider_instance_id,
                   provider_state,
                   provisioning_error
            FROM game_instances
            WHERE id = %s
            """,
            (instance["id"],),
        )
        refreshed_operation = fetch_one(
            conn,
            """
            SELECT id::text AS operation_id,
                   game_instance_id::text,
                   capability,
                   status,
                   current_stage,
                   requested_at,
                   started_at,
                   completed_at,
                   result_message
            FROM server_operations
            WHERE id = %s
            """,
            (operation["id"],),
        )

    return jsonify(
        {
            "instance": _instance_payload(refreshed_instance),
            "server_operation": _operation_payload(refreshed_operation),
            "idempotency_key": request_key,
        }
    ), 202


def _instance_payload(row):
    return {
        "id": row.get("instance_id") or row.get("id"),
        "game_server_id": row["game_server_id"],
        "name": row["name"],
        "slug": row["slug"],
        "instance_type": row["instance_type"],
        "game_identifier": row["game_identifier"],
        "status": row["status"],
        "hosting_provider": row.get("hosting_provider"),
        "provider_instance_id": row.get("provider_instance_id"),
        "provider_state": row.get("provider_state"),
        "provisioning_error": row.get("provisioning_error"),
    }


def _operation_payload(row):
    return {
        "id": row.get("operation_id") or row.get("id"),
        "instance_id": row["game_instance_id"],
        "capability": row["capability"],
        "status": row["operation_status"] if "operation_status" in row else row["status"],
        "current_stage": row["current_stage"],
        "requested_at": row["requested_at"].isoformat().replace("+00:00", "Z") if row.get("requested_at") else None,
        "started_at": row["started_at"].isoformat().replace("+00:00", "Z") if row.get("started_at") else None,
        "completed_at": row["completed_at"].isoformat().replace("+00:00", "Z") if row.get("completed_at") else None,
        "result_message": row["result_message"],
    }


def _iso(value):
    if not value:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _operation_title(capability):
    mapping = {
        "instance.status": "Status check",
        "instance.restart": "Restart",
        "instance.save": "World save",
        "instance.provision": "Provision service",
    }
    if not capability:
        return "Operation"
    return mapping.get(capability, capability.replace(".", " ").replace("_", " ").title())


def _humanize_status(status):
    if not status:
        return "Unknown"
    return str(status).replace("_", " ").title()


def _provider_label(adapter):
    labels = {
        "local_asa": "Local adapter",
        "hosting_provider": "Provider connection",
    }
    return labels.get(adapter, adapter.replace("_", " ").title() if adapter else "Provider")


def _service_health_summary(status):
    if status in {"online", "degraded", "starting"}:
        return "Healthy"
    if status in {"offline", "failed"}:
        return "Needs attention"
    return "Status unknown"
