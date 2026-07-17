from functools import wraps

from flask import Blueprint, current_app, g, jsonify

from ..auth import require_user
from ..db import fetch_all, fetch_one
from ..responses import api_error

admin_bp = Blueprint("twe_admin", __name__)


def require_admin(view):
    @wraps(view)
    @require_user
    def wrapped(*args, **kwargs):
        admin_emails = set(current_app.config["TWE_CONFIG"].admin_emails)
        if not admin_emails or g.current_user["email"].lower() not in admin_emails:
            return api_error("FORBIDDEN", "Platform admin access is required.", 403)
        return view(*args, **kwargs)

    return wrapped


@admin_bp.get("/admin/overview")
@require_admin
def admin_overview():
    with current_app.config["TWE_DB"].connect() as conn:
        row = fetch_one(
            conn,
            """
            SELECT
                count(*) FILTER (WHERE NOT (lower(email) LIKE '%%@example.test' OR lower(email) LIKE '%%@external.twe.invalid')) AS people,
                count(*) FILTER (WHERE lower(email) LIKE '%%@example.test' OR lower(email) LIKE '%%@external.twe.invalid') AS test_accounts,
                (SELECT count(*) FROM communities c
                 LEFT JOIN users creator ON creator.id = c.created_by
                 WHERE NOT COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false)) AS communities,
                (SELECT count(*) FROM communities c
                 LEFT JOIN users creator ON creator.id = c.created_by
                 WHERE COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false)) AS test_communities,
                (SELECT count(*) FROM game_servers gs
                 JOIN communities c ON c.id = gs.community_id
                 LEFT JOIN users creator ON creator.id = c.created_by
                 WHERE NOT COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false)) AS game_servers,
                (SELECT count(*) FROM game_servers gs
                 JOIN communities c ON c.id = gs.community_id
                 LEFT JOIN users creator ON creator.id = c.created_by
                 WHERE COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false)) AS test_game_servers,
                (SELECT count(*) FROM game_instances gi
                 JOIN game_servers gs ON gs.id = gi.game_server_id
                 JOIN communities c ON c.id = gs.community_id
                 LEFT JOIN users creator ON creator.id = c.created_by
                 WHERE gi.status = 'online'
                   AND NOT COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false)) AS online_instances,
                (SELECT count(*) FROM discord_instance_access_grants WHERE status = 'active') AS active_trog_grants,
                (SELECT count(*) FROM discord_instance_access_grants
                 WHERE status IN ('pending_discord_verification', 'pending_provider_approval', 'pending_bot_installation')) AS pending_trog_requests
            FROM users
            """,
        )
    return jsonify({"overview": {key: int(value) for key, value in row.items()}})


@admin_bp.get("/admin/users")
@require_admin
def admin_users():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT u.id::text,
                   u.email,
                   u.display_name,
                   u.created_at,
                   count(DISTINCT cm.id) AS community_count,
                   COALESCE(
                       array_remove(array_agg(DISTINCT uei.provider), NULL),
                       ARRAY[]::text[]
                   ) AS external_providers,
                   u.password_hash IS NOT NULL AS has_local_password,
                   (lower(u.email) LIKE '%%@example.test' OR lower(u.email) LIKE '%%@external.twe.invalid') AS is_test,
                   max(s.last_activity_at) FILTER (
                       WHERE s.revoked_at IS NULL AND s.expires_at > now()
                   ) AS last_active_at,
                   COALESCE(
                       jsonb_agg(
                           DISTINCT jsonb_build_object(
                               'id', c.id::text,
                               'name', c.name,
                               'role', cm.role
                           )
                       ) FILTER (WHERE cm.id IS NOT NULL),
                       '[]'::jsonb
                   ) AS memberships
            FROM users u
            LEFT JOIN community_memberships cm ON cm.user_id = u.id
            LEFT JOIN communities c ON c.id = cm.community_id
            LEFT JOIN user_external_identities uei ON uei.user_id = u.id
            LEFT JOIN sessions s ON s.user_id = u.id
            GROUP BY u.id
            ORDER BY (lower(u.email) LIKE '%%@example.test' OR lower(u.email) LIKE '%%@external.twe.invalid'), u.created_at DESC
            LIMIT 200
            """,
        )
    return jsonify({"users": [user_row(row) for row in rows]})


@admin_bp.get("/admin/communities")
@require_admin
def admin_communities():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT c.id::text,
                   c.name,
                   c.slug,
                   c.created_at,
                   creator.email AS created_by_email,
                   creator.display_name AS created_by_name,
                   COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false) AS is_test,
                   count(DISTINCT cm.id) AS member_count,
                   count(DISTINCT gs.id) AS game_server_count,
                   count(DISTINCT gi.id) AS instance_count,
                   COALESCE(
                       jsonb_agg(
                           DISTINCT jsonb_build_object(
                               'display_name', member.display_name,
                               'email', member.email,
                               'role', cm.role
                           )
                       ) FILTER (WHERE cm.role IN ('owner', 'admin')),
                       '[]'::jsonb
                   ) AS managers,
                   COALESCE(
                       jsonb_agg(
                           DISTINCT jsonb_build_object(
                               'id', gs.id::text,
                               'name', gs.name,
                               'game_type', gs.game_type,
                               'status', gs.status
                           )
                       ) FILTER (WHERE gs.id IS NOT NULL),
                       '[]'::jsonb
                   ) AS game_servers,
                   (SELECT count(*) FROM discord_instance_access_grants diag
                    WHERE diag.provider_community_id = c.id AND diag.status = 'active') AS active_trog_grants,
                   (SELECT count(*) FROM discord_instance_access_grants diag
                    WHERE diag.provider_community_id = c.id
                      AND diag.status IN ('pending_discord_verification', 'pending_provider_approval', 'pending_bot_installation')) AS pending_trog_requests
            FROM communities c
            LEFT JOIN users creator ON creator.id = c.created_by
            LEFT JOIN community_memberships cm ON cm.community_id = c.id
            LEFT JOIN users member ON member.id = cm.user_id
            LEFT JOIN game_servers gs ON gs.community_id = c.id
            LEFT JOIN game_instances gi ON gi.game_server_id = gs.id
            GROUP BY c.id, creator.email, creator.display_name
            ORDER BY COALESCE(lower(creator.email) LIKE '%%@example.test' OR lower(creator.email) LIKE '%%@external.twe.invalid', false), c.created_at DESC
            LIMIT 200
            """,
        )
    return jsonify({"communities": [community_row(row) for row in rows]})


@admin_bp.get("/admin/discord-access")
@require_admin
def admin_discord_access():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT diag.id::text,
                   diag.status,
                   c.name AS provider_community_name,
                   gi.name AS instance_name,
                   diag.consumer_discord_guild_name,
                   diag.consumer_discord_guild_id,
                   requester.display_name AS requested_by_name,
                   requester.email AS requested_by_email,
                   COALESCE(lower(requester.email) LIKE '%%@example.test' OR lower(requester.email) LIKE '%%@external.twe.invalid', false) AS is_test,
                   diag.created_at,
                   diag.activated_at,
                   diag.revoked_at
            FROM discord_instance_access_grants diag
            JOIN communities c ON c.id = diag.provider_community_id
            JOIN game_instances gi ON gi.id = diag.game_instance_id
            LEFT JOIN users requester ON requester.id = diag.requested_by
            ORDER BY
                CASE diag.status
                    WHEN 'pending_provider_approval' THEN 1
                    WHEN 'pending_bot_installation' THEN 2
                    WHEN 'pending_discord_verification' THEN 3
                    WHEN 'active' THEN 4
                    ELSE 5
                END,
                diag.created_at DESC
            LIMIT 200
            """,
        )
    return jsonify({"discord_access": [dict(row) for row in rows]})


def user_row(row):
    providers = list(row["external_providers"] or [])
    if row["has_local_password"]:
        providers.insert(0, "local")
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "created_at": row["created_at"],
        "community_count": int(row["community_count"]),
        "authentication_methods": providers,
        "memberships": list(row["memberships"] or []),
        "last_active_at": row["last_active_at"],
        "is_test": bool(row["is_test"]),
    }


def community_row(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "created_at": row["created_at"],
        "created_by_email": row["created_by_email"],
        "created_by_name": row["created_by_name"],
        "member_count": int(row["member_count"]),
        "game_server_count": int(row["game_server_count"]),
        "instance_count": int(row["instance_count"]),
        "managers": list(row["managers"] or []),
        "game_servers": list(row["game_servers"] or []),
        "active_trog_grants": int(row["active_trog_grants"]),
        "pending_trog_requests": int(row["pending_trog_requests"]),
        "is_test": bool(row["is_test"]),
    }
