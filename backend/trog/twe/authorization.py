from .db import fetch_one


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
            cm.id::text AS membership_id,
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
            cm.id::text AS membership_id,
            cm.role
        FROM game_servers gs
        JOIN community_memberships cm ON cm.community_id = gs.community_id
        WHERE gs.id = %s AND cm.user_id = %s
        """,
        (game_server_id, user_id),
    )


def can_request_capability(access, capability: str, conn=None) -> bool:
    if not access:
        return False
    if access["role"] == "owner":
        return True
    if conn is None:
        return False
    return bool(
        matching_capability_grant(
            conn,
            access["membership_id"],
            capability,
            access.get("game_server_id"),
            access.get("instance_id"),
        )
    )


def matching_capability_grant(conn, membership_id: str, capability: str, game_server_id: str | None, instance_id: str | None):
    return fetch_one(
        conn,
        """
        SELECT id::text
        FROM server_operation_capability_grants
        WHERE community_membership_id = %s
          AND capability = %s
          AND revoked_at IS NULL
          AND (
            game_instance_id = %s
            OR (game_instance_id IS NULL AND game_server_id = %s)
            OR (game_instance_id IS NULL AND game_server_id IS NULL)
          )
        ORDER BY
          CASE
            WHEN game_instance_id = %s THEN 1
            WHEN game_server_id = %s THEN 2
            ELSE 3
          END
        LIMIT 1
        """,
        (membership_id, capability, instance_id, game_server_id, instance_id, game_server_id),
    )
