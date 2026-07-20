from __future__ import annotations

import json
from functools import wraps
from uuid import UUID

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..services.nitrado_provider import NitradoProviderError
from ..services.provider_secret_storage import ProviderSecretStorageError


hosting_connections_bp = Blueprint("twe_hosting_connections", __name__)


def require_browser_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-TWE-CSRF") != "1":
            return api_error("CSRF_REJECTED", "The browser request could not be verified.", 403)
        return view(*args, **kwargs)

    return wrapped


@hosting_connections_bp.get("/communities/<community_id>/hosting-connections/nitrado")
@require_user
def get_nitrado_connection(community_id):
    denied = _owner_problem(community_id)
    if denied:
        return denied
    with current_app.config["TWE_DB"].connect() as conn:
        connection = fetch_one(
            conn,
            """
            SELECT pc.id::text, pc.community_id::text, pc.provider_key,
                   pc.display_name, pc.status, pc.granted_scopes, pc.connected_at,
                   pc.last_verified_at, pc.last_error_code,
                   EXISTS (SELECT 1 FROM provider_connection_secrets pcs
                           WHERE pcs.provider_connection_id = pc.id) AS has_secret
            FROM provider_connections pc
            WHERE pc.community_id = %s AND pc.provider_key = 'nitrado'
            """,
            (community_id,),
        )
        resources = _resource_rows(conn, connection["id"]) if connection else []
    return jsonify({
        "connection": _connection_response(connection) if connection else None,
        "resources": [_resource_response(row) for row in resources],
    })


@hosting_connections_bp.delete("/communities/<community_id>/hosting-connections/<connection_id>")
@require_user
@require_browser_csrf
def disconnect_hosting(community_id, connection_id):
    denied = _owner_problem(community_id)
    if denied:
        return denied
    if not _is_uuid(connection_id):
        return api_error("NOT_FOUND", "Connected hosting account was not found.", 404)

    storage = current_app.config["TWE_PROVIDER_SECRET_STORAGE"]
    try:
        with current_app.config["TWE_DB"].connect() as conn:
            with conn.transaction():
                connection = _connection_row(conn, community_id, connection_id, for_update=True)
                if not connection or connection["provider_key"] != "nitrado":
                    return api_error("NOT_FOUND", "Connected hosting account was not found.", 404)
                already_disconnected = connection["status"] == "revoked" and not connection["has_secret"]
                unbound_count = 0
                if not already_disconnected:
                    storage.delete_in_transaction(conn, connection_id)
                    unbound_count = fetch_one(
                        conn,
                        """
                        WITH unbound AS (
                            UPDATE game_servers gs
                            SET provider_resource_id = NULL, updated_at = now()
                            FROM provider_resources pr
                            WHERE gs.provider_resource_id = pr.id
                              AND pr.provider_connection_id = %s
                            RETURNING gs.id
                        )
                        SELECT count(*)::int AS count FROM unbound
                        """,
                        (connection_id,),
                    )["count"]
                    execute(
                        conn,
                        """
                        UPDATE provider_resources
                        SET available = false, selected_at = NULL, updated_at = now()
                        WHERE provider_connection_id = %s
                        """,
                        (connection_id,),
                    )
                    execute(
                        conn,
                        """
                        UPDATE provider_connections
                        SET status = 'revoked', granted_scopes = ARRAY[]::text[],
                            revoked_at = now(), last_error_code = NULL, updated_at = now()
                        WHERE id = %s
                        """,
                        (connection_id,),
                    )
                    _audit(conn, community_id, "provider.connection.nitrado_disconnected", connection_id, {
                        "provider_key": "nitrado",
                        "unbound_game_servers": unbound_count,
                        "provider_token_revoked": False,
                    })
                    connection = _connection_row(conn, community_id, connection_id)
    except ProviderSecretStorageError as exc:
        return api_error(exc.code, str(exc), 503)

    return jsonify({
        "connection": _connection_response(connection),
        "disconnected": {
            "already_disconnected": already_disconnected,
            "unbound_game_servers": unbound_count,
            "provider_token_revoked": False,
        },
    })


@hosting_connections_bp.post("/communities/<community_id>/hosting-connections/nitrado")
@require_user
@require_browser_csrf
def connect_nitrado(community_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"token"}:
        return api_error("VALIDATION_ERROR", "A Nitrado token is required.", 400)
    token = payload.get("token")
    if not isinstance(token, str) or not token.strip() or len(token.strip()) > 4096:
        return api_error("VALIDATION_ERROR", "A valid Nitrado token is required.", 400)
    denied = _owner_problem(community_id)
    if denied:
        return denied

    if not token.strip().isascii():
        return api_error("VALIDATION_ERROR", "A valid Nitrado token is required.", 400)
    credential = token.strip().encode("ascii")
    token = None
    payload["token"] = None
    if not credential:
        return api_error("VALIDATION_ERROR", "A valid Nitrado token is required.", 400)
    try:
        discovery = _discoverer().discover_resources_with_credential(credential)
    except NitradoProviderError as exc:
        credential = b""
        return api_error(exc.code, str(exc), exc.http_status)

    storage = current_app.config["TWE_PROVIDER_SECRET_STORAGE"]
    try:
        with current_app.config["TWE_DB"].connect() as conn:
            with conn.transaction():
                execute(
                    conn,
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (f"nitrado:{community_id}",),
                )
                connection = fetch_one(
                    conn,
                    """
                    SELECT pc.id::text,
                           EXISTS (SELECT 1 FROM provider_connection_secrets pcs
                                   WHERE pcs.provider_connection_id = pc.id) AS has_secret
                    FROM provider_connections pc
                    WHERE pc.community_id = %s AND pc.provider_key = 'nitrado'
                    FOR UPDATE
                    """,
                    (community_id,),
                )
                created = connection is None
                if created:
                    connection = fetch_one(
                        conn,
                        """
                        INSERT INTO provider_connections
                            (community_id, provider_key, display_name, auth_strategy, status,
                             granted_scopes, connected_by_user_id, connected_at, last_verified_at)
                        VALUES (%s, 'nitrado', 'Nitrado', 'configuration', 'active',
                                ARRAY['service']::text[], %s, now(), now())
                        RETURNING id::text, false AS has_secret
                        """,
                        (community_id, g.current_user["id"]),
                    )
                else:
                    execute(
                        conn,
                        """
                        UPDATE provider_connections
                        SET status = 'active', granted_scopes = ARRAY['service']::text[],
                            connected_by_user_id = %s, connected_at = COALESCE(connected_at, now()),
                            last_verified_at = now(), last_error_code = NULL, revoked_at = NULL,
                            updated_at = now()
                        WHERE id = %s
                        """,
                        (g.current_user["id"], connection["id"]),
                    )
                if connection["has_secret"]:
                    storage.replace_in_transaction(conn, connection["id"], credential)
                else:
                    storage.store_in_transaction(conn, connection["id"], credential)
                resources = _persist_discovery(conn, connection["id"], discovery)
                _audit_connection(conn, community_id, connection["id"], created)
                _audit_discovery(conn, community_id, connection["id"], discovery)
                response_connection = _connection_row(conn, community_id, connection["id"])
    except ProviderSecretStorageError as exc:
        return api_error(exc.code, str(exc), 503)
    finally:
        credential = b""

    return jsonify({
        "connection": _connection_response(response_connection),
        "discovery": _discovery_response(discovery, resources),
    }), 201 if created else 200


@hosting_connections_bp.post("/communities/<community_id>/hosting-connections/<connection_id>/discover")
@require_user
@require_browser_csrf
def discover_nitrado(community_id, connection_id):
    denied = _owner_problem(community_id)
    if denied:
        return denied
    with current_app.config["TWE_DB"].connect() as conn:
        connection = _connection_row(conn, community_id, connection_id)
    if not connection or connection["provider_key"] != "nitrado":
        return api_error("NOT_FOUND", "Connected hosting account was not found.", 404)

    storage = current_app.config["TWE_PROVIDER_SECRET_STORAGE"]
    credential = b""
    try:
        credential = storage.read(connection_id)
        if credential is None:
            return api_error("PROVIDER_SECRET_NOT_FOUND", "The provider credential does not exist.", 409)
        discovery = _discoverer().discover_resources_with_credential(credential)
    except NitradoProviderError as exc:
        if exc.code in {"NITRADO_AUTHENTICATION_FAILED", "NITRADO_INSUFFICIENT_SCOPE"}:
            _record_connection_error(community_id, connection_id, exc.code)
        return api_error(exc.code, str(exc), exc.http_status)
    except ProviderSecretStorageError as exc:
        return api_error(exc.code, str(exc), 503)
    finally:
        credential = b""

    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            current = _connection_row(conn, community_id, connection_id, for_update=True)
            if not current or current["provider_key"] != "nitrado":
                return api_error("NOT_FOUND", "Connected hosting account was not found.", 404)
            if current["status"] == "revoked" or not current["has_secret"]:
                return api_error(
                    "HOSTING_CONNECTION_NOT_ACTIVE",
                    "The connected hosting account is no longer active.",
                    409,
                )
            resources = _persist_discovery(conn, connection_id, discovery)
            execute(
                conn,
                """
                UPDATE provider_connections
                SET status = 'active', last_verified_at = now(), last_error_code = NULL,
                    updated_at = now()
                WHERE id = %s
                """,
                (connection_id,),
            )
            _audit_discovery(conn, community_id, connection_id, discovery)
            current = _connection_row(conn, community_id, connection_id)
    return jsonify({
        "connection": _connection_response(current),
        "discovery": _discovery_response(discovery, resources),
    })


@hosting_connections_bp.get("/communities/<community_id>/hosting-connections/<connection_id>/resources")
@require_user
def list_hosting_resources(community_id, connection_id):
    denied = _owner_problem(community_id)
    if denied:
        return denied
    with current_app.config["TWE_DB"].connect() as conn:
        connection = _connection_row(conn, community_id, connection_id)
        if not connection or connection["provider_key"] != "nitrado":
            return api_error("NOT_FOUND", "Connected hosting account was not found.", 404)
        resources = _resource_rows(conn, connection_id)
    return jsonify({
        "connection": _connection_response(connection),
        "resources": [_resource_response(row) for row in resources],
    })


@hosting_connections_bp.post(
    "/communities/<community_id>/hosting-connections/<connection_id>/resources/<resource_id>/select"
)
@require_user
@require_browser_csrf
def select_hosting_resource(community_id, connection_id, resource_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"game_server_id"}:
        return api_error("VALIDATION_ERROR", "A Game Server is required.", 400)
    game_server_id = payload.get("game_server_id")
    if not _is_uuid(game_server_id):
        return api_error("VALIDATION_ERROR", "A valid Game Server is required.", 400)
    denied = _owner_problem(community_id)
    if denied:
        return denied
    if not _is_uuid(connection_id) or not _is_uuid(resource_id):
        return api_error("NOT_FOUND", "Connected hosting resource was not found.", 404)

    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            resource = fetch_one(
                conn,
                """
                SELECT pr.id::text, pr.provider_connection_id::text,
                       pr.external_resource_id, pr.display_name, pr.resource_type,
                       pr.provider_game_key, pr.normalized_status, pr.provider_status,
                       pr.metadata, pr.available, pr.discovered_at, pr.last_seen_at,
                       pr.selected_at, pc.status AS connection_status,
                       bound.id::text AS bound_game_server_id,
                       bound.name AS bound_game_server_name,
                       bound.slug AS bound_game_server_slug
                FROM provider_resources pr
                JOIN provider_connections pc ON pc.id = pr.provider_connection_id
                LEFT JOIN game_servers bound ON bound.provider_resource_id = pr.id
                WHERE pr.id = %s AND pc.id = %s AND pc.community_id = %s
                  AND pc.provider_key = 'nitrado'
                FOR UPDATE OF pr, pc
                """,
                (resource_id, connection_id, community_id),
            )
            if not resource:
                return api_error("NOT_FOUND", "Connected hosting resource was not found.", 404)
            if resource["connection_status"] != "active":
                return api_error(
                    "HOSTING_CONNECTION_NOT_ACTIVE",
                    "The connected hosting account must be active before selecting a service.",
                    409,
                )
            if not resource["available"]:
                return api_error(
                    "PROVIDER_RESOURCE_UNAVAILABLE",
                    "The selected hosting service is no longer available.",
                    409,
                )
            if (
                resource["resource_type"] != "game_server_service"
                or resource["provider_game_key"] != "ark_survival_ascended"
            ):
                return api_error(
                    "PROVIDER_RESOURCE_UNSUPPORTED",
                    "The selected hosting service is not supported for this Game Server.",
                    409,
                )

            game_server = fetch_one(
                conn,
                """
                SELECT id::text, name, slug, game_type, game_key,
                       provider_resource_id::text
                FROM game_servers
                WHERE id = %s AND community_id = %s
                FOR UPDATE
                """,
                (game_server_id, community_id),
            )
            if not game_server:
                return api_error("NOT_FOUND", "Game Server was not found.", 404)
            if not _supports_resource(game_server, resource["provider_game_key"]):
                return api_error(
                    "GAME_SERVER_GAME_MISMATCH",
                    "The selected hosting service does not match the Game Server game.",
                    409,
                )
            if resource["bound_game_server_id"] not in {None, game_server_id}:
                return api_error(
                    "PROVIDER_RESOURCE_ALREADY_BOUND",
                    "The selected hosting service is already connected to another Game Server.",
                    409,
                )
            if game_server["provider_resource_id"] not in {None, resource_id}:
                return api_error(
                    "GAME_SERVER_ALREADY_BOUND",
                    "The Game Server is already connected to another hosting service.",
                    409,
                )

            already_bound = game_server["provider_resource_id"] == resource_id
            if not already_bound:
                execute(
                    conn,
                    """
                    UPDATE game_servers
                    SET provider_resource_id = %s, game_key = %s, updated_at = now()
                    WHERE id = %s
                    """,
                    (resource_id, resource["provider_game_key"], game_server_id),
                )
                execute(
                    conn,
                    """
                    UPDATE provider_resources
                    SET selected_at = COALESCE(selected_at, now()), updated_at = now()
                    WHERE id = %s
                    """,
                    (resource_id,),
                )
                _audit(
                    conn,
                    community_id,
                    "provider.resource.selected",
                    game_server_id,
                    {
                        "provider_key": "nitrado",
                        "provider_connection_id": connection_id,
                        "provider_resource_id": resource_id,
                        "game_server_id": game_server_id,
                        "game_key": resource["provider_game_key"],
                    },
                    target_type="game_server",
                )

            selected_resource = _resource_row(conn, connection_id, resource_id)
            selected_server = _game_server_row(conn, community_id, game_server_id)

    return jsonify({
        "binding": {
            "already_bound": already_bound,
            "game_server": _game_server_response(selected_server),
            "resource": _resource_response(selected_resource),
        }
    })


def _owner_problem(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
    if not membership or membership["role"] != "owner":
        return api_error("FORBIDDEN", "Only a Community Owner can connect hosting.", 403)
    return None


def _discoverer():
    return current_app.config["TWE_PROVIDER_REGISTRY"].credential_resource_discoverer("nitrado")


def _persist_discovery(conn, connection_id, discovery):
    execute(conn, "UPDATE provider_resources SET available = false, updated_at = now() WHERE provider_connection_id = %s", (connection_id,))
    for resource in discovery.resources:
        fetch_one(
            conn,
            """
            INSERT INTO provider_resources
                (provider_connection_id, resource_type, external_resource_id, display_name,
                 provider_game_key, normalized_status, provider_status, metadata,
                 available, discovered_at, last_seen_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, true, now(), now())
            ON CONFLICT (provider_connection_id, resource_type, external_resource_id)
            DO UPDATE SET display_name = EXCLUDED.display_name,
                          provider_game_key = EXCLUDED.provider_game_key,
                          normalized_status = EXCLUDED.normalized_status,
                          provider_status = EXCLUDED.provider_status,
                          metadata = EXCLUDED.metadata, available = true,
                          last_seen_at = now(), updated_at = now()
            RETURNING id::text
            """,
            (connection_id, resource.resource_type, resource.external_resource_id,
             resource.display_name, resource.provider_game_key, resource.normalized_status,
             resource.provider_status, json.dumps(resource.metadata)),
        )
    return _resource_rows(conn, connection_id)


def _resource_rows(conn, connection_id):
    return fetch_all(
        conn,
        """
        SELECT pr.id::text, pr.external_resource_id, pr.display_name,
               pr.provider_game_key, pr.normalized_status, pr.provider_status,
               pr.metadata, pr.available, pr.discovered_at, pr.last_seen_at,
               pr.selected_at, gs.id::text AS bound_game_server_id,
               gs.name AS bound_game_server_name, gs.slug AS bound_game_server_slug
        FROM provider_resources pr
        LEFT JOIN game_servers gs ON gs.provider_resource_id = pr.id
        WHERE pr.provider_connection_id = %s
        ORDER BY (pr.provider_game_key = 'ark_survival_ascended') DESC, pr.display_name, pr.id
        """,
        (connection_id,),
    )


def _resource_row(conn, connection_id, resource_id):
    return fetch_one(
        conn,
        """
        SELECT pr.id::text, pr.external_resource_id, pr.display_name,
               pr.provider_game_key, pr.normalized_status, pr.provider_status,
               pr.metadata, pr.available, pr.discovered_at, pr.last_seen_at,
               pr.selected_at, gs.id::text AS bound_game_server_id,
               gs.name AS bound_game_server_name, gs.slug AS bound_game_server_slug
        FROM provider_resources pr
        LEFT JOIN game_servers gs ON gs.provider_resource_id = pr.id
        WHERE pr.provider_connection_id = %s AND pr.id = %s
        """,
        (connection_id, resource_id),
    )


def _game_server_row(conn, community_id, game_server_id):
    return fetch_one(
        conn,
        """
        SELECT id::text, name, slug, game_type, game_key,
               provider_resource_id::text
        FROM game_servers
        WHERE community_id = %s AND id = %s
        """,
        (community_id, game_server_id),
    )


def _connection_row(conn, community_id, connection_id, for_update=False):
    lock = " FOR UPDATE" if for_update else ""
    return fetch_one(
        conn,
        """
        SELECT pc.id::text, pc.community_id::text, pc.provider_key,
               pc.display_name, pc.status, pc.granted_scopes, pc.connected_at,
               pc.last_verified_at, pc.last_error_code,
               EXISTS (SELECT 1 FROM provider_connection_secrets pcs
                       WHERE pcs.provider_connection_id = pc.id) AS has_secret
        FROM provider_connections pc
        WHERE pc.id = %s AND pc.community_id = %s
        """ + lock,
        (connection_id, community_id),
    )


def _connection_response(row):
    return {
        "id": row["id"], "provider": "nitrado", "display_name": row["display_name"],
        "status": row["status"], "granted_scopes": list(row["granted_scopes"]),
        "connected_at": _iso(row["connected_at"]),
        "last_verified_at": _iso(row["last_verified_at"]),
        "last_error_code": row["last_error_code"],
        "credential": {
            "configured": bool(row["has_secret"]),
            "masked": bool(row["has_secret"]),
        },
    }


def _resource_response(row):
    return {
        "id": row["id"], "service_id": row["external_resource_id"],
        "name": row["display_name"], "game_key": row["provider_game_key"],
        "supported": row["provider_game_key"] == "ark_survival_ascended",
        "status": row["normalized_status"], "provider_status": row["provider_status"],
        "metadata": row["metadata"], "available": row["available"],
        "discovered_at": _iso(row["discovered_at"]), "last_seen_at": _iso(row["last_seen_at"]),
        "selected_at": _iso(row["selected_at"]),
        "binding": {
            "game_server_id": row["bound_game_server_id"],
            "game_server_name": row["bound_game_server_name"],
            "game_server_slug": row["bound_game_server_slug"],
        } if row["bound_game_server_id"] else None,
    }


def _game_server_response(row):
    return {
        "id": row["id"], "name": row["name"], "slug": row["slug"],
        "game_type": row["game_type"], "game_key": row["game_key"],
        "provider_resource_id": row["provider_resource_id"],
    }


def _discovery_response(discovery, resources):
    return {
        "total_services": discovery.total_services,
        "supported_services": sum(1 for row in resources if row["provider_game_key"] == "ark_survival_ascended" and row["available"]),
        "unsupported_services": discovery.unsupported_services,
        "omitted_services": discovery.omitted_services,
        "resources": [_resource_response(row) for row in resources],
    }


def _audit_connection(conn, community_id, connection_id, created):
    _audit(conn, community_id,
           "provider.connection.nitrado_created" if created else "provider.connection.nitrado_token_replaced",
           connection_id, {"provider_key": "nitrado", "granted_scopes": ["service"]})


def _audit_discovery(conn, community_id, connection_id, discovery):
    _audit(conn, community_id, "provider.discovery.completed", connection_id, {
        "provider_key": "nitrado", "total_services": discovery.total_services,
        "resource_count": len(discovery.resources),
        "unsupported_services": discovery.unsupported_services,
        "omitted_services": discovery.omitted_services,
    })


def _audit(conn, community_id, action, target_id, details, target_type="provider_connection"):
    execute(
        conn,
        """
        INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (g.current_user["id"], community_id, action, target_type, target_id, json.dumps(details)),
    )


def _record_connection_error(community_id, connection_id, error_code):
    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            execute(
                conn,
                """
                UPDATE provider_connections
                SET status = 'reauthorization_required', last_error_code = %s, updated_at = now()
                WHERE id = %s AND community_id = %s AND provider_key = 'nitrado'
                """,
                (error_code, connection_id, community_id),
            )


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def _is_uuid(value):
    try:
        UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return False
    return True


def _supports_resource(game_server, provider_game_key):
    if game_server["game_key"]:
        return game_server["game_key"] == provider_game_key
    normalized_game_type = "".join(
        character.lower()
        for character in game_server["game_type"]
        if character.isalnum()
    )
    return provider_game_key == "ark_survival_ascended" and normalized_game_type == "arksurvivalascended"
