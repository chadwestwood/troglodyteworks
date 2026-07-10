from flask import Blueprint, current_app, g, jsonify

from ..auth import require_user
from ..authorization import instance_access
from ..db import fetch_all, fetch_one
from ..responses import api_error
from ..serializers import iso, operation_with_requester

operations_bp = Blueprint("twe_operations", __name__)


@operations_bp.get("/server-operations/<operation_id>")
@require_user
def get_operation(operation_id):
    with current_app.config["TWE_DB"].connect() as conn:
        operation = fetch_one(
            conn,
            """
            SELECT so.id::text, so.game_instance_id::text, so.requested_by::text, so.capability,
                   so.status, so.current_stage, so.requested_at, so.started_at, so.completed_at,
                   so.result_message, users.display_name AS requested_by_display_name
            FROM server_operations so
            JOIN users ON users.id = so.requested_by
            WHERE so.id = %s
            """,
            (operation_id,),
        )
        if not operation:
            return api_error("NOT_FOUND", "Server Operation was not found.", 404)
        if not instance_access(conn, g.current_user["id"], operation["game_instance_id"]):
            return api_error("FORBIDDEN", "You do not have access to this Server Operation.", 403)
        checks = fetch_all(
            conn,
            """
            SELECT id::text, name, status, started_at, completed_at, result_message, sort_order
            FROM server_operation_checks
            WHERE server_operation_id = %s
            ORDER BY sort_order, name
            """,
            (operation_id,),
        )
    data = operation_with_requester(operation)
    data["checks"] = [
        {
            "id": check["id"],
            "name": check["name"],
            "status": check["status"],
            "started_at": iso(check["started_at"]),
            "completed_at": iso(check["completed_at"]),
            "result_message": check["result_message"],
            "sort_order": check["sort_order"],
        }
        for check in checks
    ]
    return jsonify({"server_operation": data})
