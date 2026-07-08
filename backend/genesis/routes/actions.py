from flask import Blueprint, jsonify
from services.ark_settings import get_server_settings

actions_bp = Blueprint("actions", __name__)

@actions_bp.route("/refresh", methods=["POST"])
def refresh():
    return jsonify({
        "success": True,
        "message": "Settings refreshed.",
        "data": get_server_settings()
    })
