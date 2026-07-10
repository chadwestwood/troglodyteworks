from .db import fetch_one


MANAGE_ROLES = {"owner", "admin"}
VIEW_ROLES = {"owner", "admin", "moderator", "member"}


def membership_for_community(conn, user_id: str, community_id: str):
    return fetch_one(
        conn,
        """
        SELECT id::text, role
        FROM community_memberships
        WHERE user_id = %s AND community_id = %s
        """,
        (user_id, community_id),
    )


def instance_access(conn, user_id: str, instance_id: str):
    return fetch_one(
        conn,
        """
        SELECT
            gi.id::text AS instance_id,
            gi.name AS instance_name,
            gi.slug AS instance_slug,
            gi.instance_type,
            gi.game_identifier,
            gi.status AS instance_status,
            gs.id::text AS game_server_id,
            gs.name AS game_server_name,
            gs.slug AS game_server_slug,
            gs.game_type,
            gs.management_adapter,
            gs.status AS game_server_status,
            c.id::text AS community_id,
            c.name AS community_name,
            cm.role AS role
        FROM game_instances gi
        JOIN game_servers gs ON gs.id = gi.game_server_id
        JOIN communities c ON c.id = gs.community_id
        JOIN community_memberships cm ON cm.community_id = c.id
        WHERE gi.id = %s AND cm.user_id = %s
        """,
        (instance_id, user_id),
    )


def game_server_access(conn, user_id: str, game_server_id: str):
    return fetch_one(
        conn,
        """
        SELECT
            gs.id::text AS game_server_id,
            gs.community_id::text,
            gs.name,
            gs.slug,
            gs.game_type,
            gs.management_adapter,
            gs.status,
            cm.role
        FROM game_servers gs
        JOIN community_memberships cm ON cm.community_id = gs.community_id
        WHERE gs.id = %s AND cm.user_id = %s
        """,
        (game_server_id, user_id),
    )


def can_request_capability(role: str, capability: str) -> bool:
    if capability == "instance.status":
        return role in VIEW_ROLES
    return role in MANAGE_ROLES
