from flask import Blueprint, current_app, g, jsonify

from ..auth import require_user
from ..authorization import game_server_access
from ..db import fetch_all
from ..responses import api_error

game_servers_bp = Blueprint("twe_game_servers", __name__)


@game_servers_bp.get("/game-servers/<game_server_id>")
@require_user
def get_game_server(game_server_id):
    with current_app.config["TWE_DB"].connect() as conn:
        row = game_server_access(conn, g.current_user["id"], game_server_id)
        if not row:
            return api_error("NOT_FOUND", "Game Server was not found.", 404)
    return jsonify(
        {
            "game_server": {
                "id": row["game_server_id"],
                "community_id": row["community_id"],
                "name": row["name"],
                "slug": row["slug"],
                "game_type": row["game_type"],
                "management_adapter": row["management_adapter"],
                "status": row["status"],
            }
        }
    )


@game_servers_bp.get("/game-servers/<game_server_id>/instances")
@require_user
def list_instances(game_server_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not game_server_access(conn, g.current_user["id"], game_server_id):
            return api_error("NOT_FOUND", "Game Server was not found.", 404)
        rows = fetch_all(
            conn,
            """
            SELECT id::text, game_server_id::text, name, slug, instance_type, game_identifier, status, sort_order
            FROM game_instances
            WHERE game_server_id = %s
            ORDER BY sort_order, name
            """,
            (game_server_id,),
        )
    return jsonify({"instances": rows})
