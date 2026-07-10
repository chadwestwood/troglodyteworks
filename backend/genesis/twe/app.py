from pathlib import Path

from flask import Flask, send_from_directory

from .config import load_config
from .db import Database
from .responses import api_error
from .routes.auth import auth_bp
from .routes.communities import communities_bp
from .routes.game_servers import game_servers_bp
from .routes.instances import instances_bp
from .routes.operations import operations_bp


def create_app(config=None, database=None):
    app = Flask(__name__)
    twe_config = config or load_config()
    app.config["TWE_CONFIG"] = twe_config
    app.config["TWE_DB"] = database or Database(twe_config.database_url)

    app.register_blueprint(auth_bp, url_prefix="/api/v1")
    app.register_blueprint(communities_bp, url_prefix="/api/v1")
    app.register_blueprint(game_servers_bp, url_prefix="/api/v1")
    app.register_blueprint(instances_bp, url_prefix="/api/v1")
    app.register_blueprint(operations_bp, url_prefix="/api/v1")

    site_root = Path(__file__).resolve().parents[3] / "site"

    @app.get("/")
    def site_index():
        return send_from_directory(site_root, "index.html")

    @app.get("/<path:path>")
    def site_file(path):
        target = site_root / path
        if target.is_dir():
            target = target / "index.html"
        if target.exists() and target.is_file():
            return send_from_directory(site_root, str(target.relative_to(site_root)))
        return api_error("NOT_FOUND", "Resource was not found.", 404)

    @app.errorhandler(404)
    def not_found(_error):
        return api_error("NOT_FOUND", "Resource was not found.", 404)

    @app.errorhandler(Exception)
    def internal_error(_error):
        app.logger.exception("Unhandled application error")
        return api_error("INTERNAL_ERROR", "An internal error occurred.", 500)

    return app
