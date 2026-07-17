from flask import Blueprint, jsonify
from services.ark_settings import get_server_settings

genesis_bp = Blueprint("genesis", __name__)

@genesis_bp.route("/settings", methods=["GET"])
def settings():
    return jsonify(get_server_settings())

@genesis_bp.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "genesis-instance-service"
    })
