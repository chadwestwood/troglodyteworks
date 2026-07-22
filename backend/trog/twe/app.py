from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import load_config
from .db import Database
from .db import fetch_all
from .responses import api_error
from .rate_limits import (
    consume_request_limit,
    rate_limit_response,
    request_identifier,
    rule_for_request,
)
from .services.provider_secret_storage import build_provider_secret_storage
from .routes.account_identities import account_identities_bp
from .routes.admin import admin_bp
from .routes.auth import auth_bp
from .routes.communities import communities_bp
from .routes.community_invitations import community_invitations_bp
from .routes.discord_access import discord_access_bp
from .routes.game_catalog import game_catalog_bp
from .routes.game_servers import game_servers_bp
from .routes.hosting_connections import hosting_connections_bp
from .routes.instances import instances_bp
from .routes.operations import operations_bp
from .services.provider_registry import build_provider_registry
from .services.runtime_heartbeat import runtime_heartbeat_response


def create_app(config=None, database=None, provider_registry=None):
    app = Flask(__name__)
    twe_config = config or load_config()
    app.config["TWE_CONFIG"] = twe_config
    app.config["TWE_DB"] = database or Database(twe_config.database_url)
    app.config["TWE_PROVIDER_SECRET_STORAGE"] = build_provider_secret_storage(
        twe_config,
        app.config["TWE_DB"],
    )
    app.config["TWE_PROVIDER_REGISTRY"] = provider_registry or build_provider_registry(twe_config)

    app.register_blueprint(auth_bp, url_prefix="/api/v1")
    app.register_blueprint(account_identities_bp, url_prefix="/api/v1")
    app.register_blueprint(admin_bp, url_prefix="/api/v1")
    app.register_blueprint(communities_bp, url_prefix="/api/v1")
    app.register_blueprint(community_invitations_bp, url_prefix="/api/v1")
    app.register_blueprint(discord_access_bp, url_prefix="/api/v1")
    app.register_blueprint(game_catalog_bp, url_prefix="/api/v1")
    app.register_blueprint(game_servers_bp, url_prefix="/api/v1")
    app.register_blueprint(hosting_connections_bp, url_prefix="/api/v1")
    app.register_blueprint(instances_bp, url_prefix="/api/v1")
    app.register_blueprint(operations_bp, url_prefix="/api/v1")

    site_root = Path(__file__).resolve().parents[3] / "site"

    @app.before_request
    def enforce_request_rate_limit():
        if request.url_rule is None:
            return None
        rule = rule_for_request(request.method, request.path)
        if not rule:
            return None
        with app.config["TWE_DB"].connect() as conn:
            # Lightweight unit-test database doubles intentionally do not
            # implement a PostgreSQL cursor. Production Database connections do.
            if not callable(getattr(conn, "cursor", None)):
                return None
            allowed, retry_after = consume_request_limit(conn, rule, request_identifier())
        if not allowed:
            return rate_limit_response(retry_after)
        return None

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    @app.get("/health/ready")
    def readiness_check():
        with app.config["TWE_DB"].connect() as conn:
            rows = fetch_all(
                conn,
                """
                SELECT component, status, details, checked_at
                FROM runtime_heartbeats
                WHERE component = 'trog_worker'
                """,
            )
        worker = runtime_heartbeat_response(rows)
        worker_ready = bool(worker and worker[0]["status"] == "ready")
        status_code = 200 if worker_ready else 503
        return jsonify({
            "status": "ready" if worker_ready else "degraded",
            "components": {
                "web_api": "ready",
                "database": "ready",
                "trog_worker": worker[0]["status"] if worker else "missing",
            },
        }), status_code

    @app.get("/")
    def site_index():
        return send_from_directory(site_root, "index.html")

    @app.get("/invite/<token>/")
    def invite_page(token):
        return send_from_directory(site_root, "invite/index.html")

    # Community pages use the selected Community from the API. Serve the shared
    # page shells for every real slug so one user's Communities remain visibly
    # distinct without duplicating static HTML for each Community.
    @app.get("/communities/<community_slug>/")
    def community_page(community_slug):
        return send_from_directory(site_root, "communities/cohorts-in-the-wild/index.html")

    @app.get("/communities/<community_slug>/hosting/")
    def community_hosting_page(community_slug):
        return send_from_directory(site_root, "communities/cohorts-in-the-wild/hosting/index.html")

    @app.get("/communities/<community_slug>/invitations/")
    def community_invitations_page(community_slug):
        return send_from_directory(site_root, "communities/cohorts-in-the-wild/invitations/index.html")

    @app.get("/communities/<community_slug>/game-servers/<game_slug>/")
    def community_game_server_page(community_slug, game_slug):
        return send_from_directory(site_root, "communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/index.html")

    @app.get("/communities/<community_slug>/game-servers/<game_slug>/instances/<instance_slug>/")
    def community_instance_page(community_slug, game_slug, instance_slug):
        return send_from_directory(site_root, "communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/instances/genesis/index.html")

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

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return api_error("NOT_FOUND", "Resource was not found.", 404)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return api_error("INTERNAL_ERROR", "An internal error occurred.", error.code or 500)

    @app.errorhandler(Exception)
    def internal_error(_error):
        app.logger.exception("Unhandled application error")
        return api_error("INTERNAL_ERROR", "An internal error occurred.", 500)

    return app
