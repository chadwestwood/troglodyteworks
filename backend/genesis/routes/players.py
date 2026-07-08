from flask import Blueprint, jsonify
from services.rcon import list_players

players_bp = Blueprint("players", __name__)

@players_bp.route("/players", methods=["GET"])
def players():
    try:
        data = list_players()
        return jsonify({
            "success": True,
            "online": len(data["players"]),
            "players": data["players"],
            "raw": data["raw"]
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "online": 0,
            "players": []
        }), 500
