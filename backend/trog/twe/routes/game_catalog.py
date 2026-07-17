from flask import Blueprint, jsonify

from ..auth import require_user
from ..services.game_catalog import game_catalog


game_catalog_bp = Blueprint("twe_game_catalog", __name__)


@game_catalog_bp.get("/game-catalog")
@require_user
def get_game_catalog():
    return jsonify(game_catalog())
