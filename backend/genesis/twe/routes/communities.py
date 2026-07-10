from flask import Blueprint, current_app, g, jsonify

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import fetch_all, fetch_one
from ..responses import api_error

communities_bp = Blueprint("twe_communities", __name__)


@communities_bp.get("/communities")
@require_user
def list_communities():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT c.id::text, c.name, c.slug, cm.role
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
