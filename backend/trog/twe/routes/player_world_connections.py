from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from functools import wraps
import re
import secrets
from uuid import UUID

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..security import hash_session_token


player_world_connections_bp = Blueprint("twe_player_world_connections", __name__)

PAIRING_LIFETIME = timedelta(minutes=15)
MAX_REQUEST_BYTES = 64 * 1024
MAX_EVENTS_PER_REQUEST = 50
WORLD_FINGERPRINT = re.compile(r"^[a-f0-9]{64}$")
EVENT_PAYLOAD_FIELDS = {
    "client.started": frozenset(),
    "client.stopped": frozenset(),
    "world.joined": frozenset({"world_label", "server_fingerprint", "connection_kind"}),
    "world.left": frozenset(),
    "heartbeat": frozenset({"world_label", "server_fingerprint", "connection_kind"}),
}


def require_browser_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-TWE-CSRF") != "1":
            return api_error("CSRF_REJECTED", "The browser request could not be verified.", 403)
        return view(*args, **kwargs)

    return wrapped


@player_world_connections_bp.post("/communities/<community_id>/player-world-connections")
@require_user
@require_browser_csrf
def create_player_world_connection(community_id):
    payload = request.get_json(silent=True) or {}
    display_name = normalize_short_text(payload.get("display_name"), 120)
    if not display_name:
        return api_error("VALIDATION_ERROR", "A connection name is required.", 400)
    if payload.get("game_type", "minecraft") != "minecraft":
        return api_error("VALIDATION_ERROR", "Minecraft is the only supported player connection right now.", 400)

    pairing_token = new_prefixed_token("trog_pair_")
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership:
            return api_error("FORBIDDEN", "You must belong to this Community.", 403)
        connection = fetch_one(
            conn,
            """
            INSERT INTO player_world_connections (community_id, owner_user_id, display_name)
            VALUES (%s, %s, %s)
            RETURNING id::text, community_id::text, owner_user_id::text, display_name,
                      game_type, source_kind, status, discord_sharing_enabled,
                      last_seen_at, created_at, updated_at, revoked_at
            """,
            (community_id, g.current_user["id"], display_name),
        )
        store_pairing_token(conn, connection["id"], g.current_user["id"], pairing_token)
        audit_connection(conn, g.current_user["id"], community_id, "player_world_connection.create", connection["id"])

    response = connection_response(connection)
    response["pairing"] = pairing_response(pairing_token)
    return jsonify({"player_world_connection": response}), 201


@player_world_connections_bp.get("/communities/<community_id>/player-world-connections")
@require_user
def list_player_world_connections(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not membership_for_community(conn, g.current_user["id"], community_id):
            return api_error("FORBIDDEN", "You do not have access to this Community.", 403)
        rows = fetch_all(
            conn,
            """
            SELECT pwc.id::text, pwc.community_id::text, pwc.owner_user_id::text,
                   pwc.display_name, pwc.game_type, pwc.source_kind, pwc.status,
                   pwc.discord_sharing_enabled, pwc.last_seen_at, pwc.created_at,
                   pwc.updated_at, pwc.revoked_at, users.display_name AS owner_display_name
            FROM player_world_connections pwc
            JOIN users ON users.id = pwc.owner_user_id
            WHERE pwc.community_id = %s
            ORDER BY lower(pwc.display_name), pwc.created_at
            """,
            (community_id,),
        )
    return jsonify({"player_world_connections": [connection_response(row) for row in rows]})


@player_world_connections_bp.post("/player-world-connections/<connection_id>/pairing-token")
@require_user
@require_browser_csrf
def create_pairing_token(connection_id):
    pairing_token = new_prefixed_token("trog_pair_")
    with current_app.config["TWE_DB"].connect() as conn:
        connection = owned_connection(conn, connection_id, g.current_user["id"])
        if not connection:
            return api_error("NOT_FOUND", "Player World Connection was not found.", 404)
        if connection["status"] == "revoked":
            return api_error("CONNECTION_REVOKED", "This connection has been revoked.", 409)
        execute(
            conn,
            """
            UPDATE player_world_pairing_tokens
            SET consumed_at = coalesce(consumed_at, now())
            WHERE player_world_connection_id = %s AND consumed_at IS NULL
            """,
            (connection_id,),
        )
        store_pairing_token(conn, connection_id, g.current_user["id"], pairing_token)
        audit_connection(
            conn,
            g.current_user["id"],
            connection["community_id"],
            "player_world_connection.pairing_token.create",
            connection_id,
        )
    return jsonify({"pairing": pairing_response(pairing_token)}), 201


@player_world_connections_bp.delete("/player-world-connections/<connection_id>")
@require_user
@require_browser_csrf
def revoke_player_world_connection(connection_id):
    with current_app.config["TWE_DB"].connect() as conn:
        connection = accessible_connection(conn, connection_id, g.current_user["id"])
        if not connection:
            return api_error("NOT_FOUND", "Player World Connection was not found.", 404)
        may_revoke = connection["owner_user_id"] == g.current_user["id"] or connection["role"] in {"owner", "admin"}
        if not may_revoke:
            return api_error("FORBIDDEN", "Only the connection owner or a Community leader may revoke it.", 403)
        execute(
            conn,
            """
            UPDATE player_world_connections
            SET status = 'revoked', revoked_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (connection_id,),
        )
        execute(
            conn,
            "UPDATE player_world_devices SET revoked_at = coalesce(revoked_at, now()) WHERE player_world_connection_id = %s",
            (connection_id,),
        )
        execute(
            conn,
            "UPDATE player_world_pairing_tokens SET consumed_at = coalesce(consumed_at, now()) WHERE player_world_connection_id = %s",
            (connection_id,),
        )
        audit_connection(
            conn,
            g.current_user["id"],
            connection["community_id"],
            "player_world_connection.revoke",
            connection_id,
        )
    return jsonify({"player_world_connection": {"id": connection_id, "status": "revoked"}})


@player_world_connections_bp.get("/player-world-connections/<connection_id>/discord-bindings")
@require_user
def list_discord_bindings(connection_id):
    with current_app.config["TWE_DB"].connect() as conn:
        connection = owned_connection(conn, connection_id, g.current_user["id"])
        if not connection:
            return api_error("NOT_FOUND", "Player World Connection was not found.", 404)
        rows = fetch_all(
            conn,
            """
            SELECT verification.discord_guild_id,
                   verification.discord_guild_name,
                   verification.authority_source,
                   installation.id::text AS installation_id,
                   binding.id::text AS binding_id,
                   binding.status AS binding_status
            FROM discord_guild_authority_verifications verification
            LEFT JOIN discord_guild_installations installation
              ON installation.discord_guild_id = verification.discord_guild_id
             AND installation.community_id = %s
            LEFT JOIN discord_player_world_bindings binding
              ON binding.discord_guild_installation_id = installation.id
             AND binding.player_world_connection_id = %s
             AND binding.status = 'active'
            WHERE verification.user_id = %s
              AND verification.can_manage_guild = true
              AND verification.expires_at > now()
            ORDER BY lower(verification.discord_guild_name), verification.discord_guild_id
            """,
            (connection["community_id"], connection_id, g.current_user["id"]),
        )
    return jsonify(
        {
            "discord_guilds": [
                {
                    "id": row["discord_guild_id"],
                    "name": row["discord_guild_name"] or "Discord server",
                    "authority_source": row["authority_source"],
                    "trog_installed_for_community": bool(row["installation_id"]),
                    "binding_id": row["binding_id"],
                    "sharing_active": row["binding_status"] == "active",
                }
                for row in rows
            ]
        }
    )


@player_world_connections_bp.post("/player-world-connections/<connection_id>/discord-bindings")
@require_user
@require_browser_csrf
def create_discord_binding(connection_id):
    payload = request.get_json(silent=True) or {}
    discord_guild_id = str(payload.get("discord_guild_id", "")).strip()
    if not discord_guild_id.isdigit() or len(discord_guild_id) > 20:
        return api_error("VALIDATION_ERROR", "A valid Discord server is required.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        connection = owned_connection(conn, connection_id, g.current_user["id"])
        if not connection:
            return api_error("NOT_FOUND", "Player World Connection was not found.", 404)
        if connection["status"] == "revoked":
            return api_error("CONNECTION_REVOKED", "This connection has been revoked.", 409)
        installation = fetch_one(
            conn,
            """
            SELECT installation.id::text, installation.community_id::text
            FROM discord_guild_installations installation
            JOIN discord_guild_authority_verifications verification
              ON verification.discord_guild_id = installation.discord_guild_id
             AND verification.user_id = %s
             AND verification.can_manage_guild = true
             AND verification.expires_at > now()
            WHERE installation.discord_guild_id = %s
              AND installation.community_id = %s
            """,
            (g.current_user["id"], discord_guild_id, connection["community_id"]),
        )
        if not installation:
            return api_error(
                "DISCORD_AUTHORITY_REQUIRED",
                "Trog must already be installed for this Community, and your Discord administrator authority must be current.",
                403,
            )
        execute(
            conn,
            """
            UPDATE discord_player_world_bindings
            SET status = 'revoked', revoked_at = now(), updated_at = now()
            WHERE discord_guild_installation_id = %s
              AND player_world_connection_id = %s
              AND status = 'active'
            """,
            (installation["id"], connection_id),
        )
        binding = fetch_one(
            conn,
            """
            INSERT INTO discord_player_world_bindings
                (discord_guild_installation_id, player_world_connection_id, community_id, authorized_by_user_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id::text, status, created_at
            """,
            (installation["id"], connection_id, connection["community_id"], g.current_user["id"]),
        )
        execute(
            conn,
            "UPDATE player_world_connections SET discord_sharing_enabled = true, updated_at = now() WHERE id = %s",
            (connection_id,),
        )
        audit_connection(
            conn,
            g.current_user["id"],
            connection["community_id"],
            "player_world_connection.discord.bind",
            connection_id,
            {"discord_guild_id": discord_guild_id, "binding_id": binding["id"]},
        )
    return jsonify({"discord_binding": {**binding, "discord_guild_id": discord_guild_id}}), 201


@player_world_connections_bp.delete("/player-world-connections/<connection_id>/discord-bindings/<binding_id>")
@require_user
@require_browser_csrf
def revoke_discord_binding(connection_id, binding_id):
    with current_app.config["TWE_DB"].connect() as conn:
        connection = owned_connection(conn, connection_id, g.current_user["id"])
        if not connection:
            return api_error("NOT_FOUND", "Player World Connection was not found.", 404)
        binding = fetch_one(
            conn,
            """
            UPDATE discord_player_world_bindings
            SET status = 'revoked', revoked_at = now(), updated_at = now()
            WHERE id = %s AND player_world_connection_id = %s AND status = 'active'
            RETURNING id::text
            """,
            (binding_id, connection_id),
        )
        if not binding:
            return api_error("NOT_FOUND", "Discord sharing binding was not found.", 404)
        remaining = fetch_one(
            conn,
            """
            SELECT id::text FROM discord_player_world_bindings
            WHERE player_world_connection_id = %s AND status = 'active'
            LIMIT 1
            """,
            (connection_id,),
        )
        execute(
            conn,
            "UPDATE player_world_connections SET discord_sharing_enabled = %s, updated_at = now() WHERE id = %s",
            (bool(remaining), connection_id),
        )
        audit_connection(
            conn,
            g.current_user["id"],
            connection["community_id"],
            "player_world_connection.discord.revoke",
            connection_id,
            {"binding_id": binding_id},
        )
    return jsonify({"discord_binding": {"id": binding_id, "status": "revoked"}})


@player_world_connections_bp.post("/minecraft-client/pair")
def pair_minecraft_client():
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return api_error("PAYLOAD_TOO_LARGE", "The pairing request is too large.", 413)
    payload = request.get_json(silent=True) or {}
    pairing_token = normalize_short_text(payload.get("pairing_token"), 200)
    device_name = normalize_short_text(payload.get("device_name") or "Minecraft client", 120)
    minecraft_version = normalize_short_text(payload.get("minecraft_version"), 40)
    mod_version = normalize_short_text(payload.get("mod_version"), 40)
    if not all((pairing_token, device_name, minecraft_version, mod_version)):
        return api_error("VALIDATION_ERROR", "Pairing token, device name, and version fields are required.", 400)

    device_token = new_prefixed_token("trog_device_")
    with current_app.config["TWE_DB"].connect() as conn:
        pairing = fetch_one(
            conn,
            """
            SELECT pwt.id::text, pwt.player_world_connection_id::text,
                   pwc.community_id::text, pwc.display_name, pwc.status
            FROM player_world_pairing_tokens pwt
            JOIN player_world_connections pwc ON pwc.id = pwt.player_world_connection_id
            WHERE pwt.token_hash = %s
              AND pwt.consumed_at IS NULL
              AND pwt.expires_at > now()
            FOR UPDATE OF pwt
            """,
            (hash_session_token(pairing_token),),
        )
        if not pairing or pairing["status"] == "revoked":
            return api_error("PAIRING_INVALID", "The pairing token is invalid or expired.", 401)
        execute(
            conn,
            """
            UPDATE player_world_devices
            SET revoked_at = coalesce(revoked_at, now())
            WHERE player_world_connection_id = %s AND revoked_at IS NULL
            """,
            (pairing["player_world_connection_id"],),
        )
        device = fetch_one(
            conn,
            """
            INSERT INTO player_world_devices
                (player_world_connection_id, device_name, device_token_hash, minecraft_version, mod_version)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id::text
            """,
            (
                pairing["player_world_connection_id"],
                device_name,
                hash_session_token(device_token),
                minecraft_version,
                mod_version,
            ),
        )
        execute(conn, "UPDATE player_world_pairing_tokens SET consumed_at = now() WHERE id = %s", (pairing["id"],))
        execute(
            conn,
            """
            UPDATE player_world_connections
            SET status = 'offline', updated_at = now()
            WHERE id = %s
            """,
            (pairing["player_world_connection_id"],),
        )
        audit_connection(
            conn,
            None,
            pairing["community_id"],
            "player_world_connection.device.pair",
            pairing["player_world_connection_id"],
            {"device_id": device["id"]},
        )
    return jsonify(
        {
            "device": {
                "id": device["id"],
                "token": device_token,
                "player_world_connection_id": pairing["player_world_connection_id"],
                "connection_name": pairing["display_name"],
            }
        }
    ), 201


@player_world_connections_bp.post("/minecraft-client/events")
def ingest_minecraft_client_events():
    if request.content_length is not None and request.content_length > MAX_REQUEST_BYTES:
        return api_error("PAYLOAD_TOO_LARGE", "The event request is too large.", 413)
    token = bearer_token()
    if not token:
        return api_error("DEVICE_UNAUTHENTICATED", "A device bearer token is required.", 401)
    payload = request.get_json(silent=True) or {}
    raw_events = payload.get("events")
    if not isinstance(raw_events, list) or not 1 <= len(raw_events) <= MAX_EVENTS_PER_REQUEST:
        return api_error("VALIDATION_ERROR", "Provide between 1 and 50 events.", 400)
    try:
        events = [normalize_event(event) for event in raw_events]
    except ValueError as exc:
        return api_error("VALIDATION_ERROR", str(exc), 400)

    with current_app.config["TWE_DB"].connect() as conn:
        device = fetch_one(
            conn,
            """
            SELECT pwd.id::text, pwd.player_world_connection_id::text
            FROM player_world_devices pwd
            JOIN player_world_connections pwc ON pwc.id = pwd.player_world_connection_id
            WHERE pwd.device_token_hash = %s
              AND pwd.revoked_at IS NULL
              AND pwc.revoked_at IS NULL
            """,
            (hash_session_token(token),),
        )
        if not device:
            return api_error("DEVICE_UNAUTHENTICATED", "The device credential is invalid or revoked.", 401)

        accepted = 0
        for event in events:
            inserted = fetch_one(
                conn,
                """
                INSERT INTO player_world_events
                    (player_world_connection_id, player_world_device_id, client_event_id,
                     event_type, occurred_at, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (player_world_device_id, client_event_id) DO NOTHING
                RETURNING id::text
                """,
                (
                    device["player_world_connection_id"],
                    device["id"],
                    event["event_id"],
                    event["event_type"],
                    event["occurred_at"],
                    json.dumps(event["payload"], separators=(",", ":")),
                ),
            )
            accepted += 1 if inserted else 0

        latest = fetch_one(
            conn,
            """
            SELECT event_type
            FROM player_world_events
            WHERE player_world_connection_id = %s
            ORDER BY occurred_at DESC, received_at DESC, id DESC
            LIMIT 1
            """,
            (device["player_world_connection_id"],),
        )
        status = status_for_event(latest["event_type"])
        execute(
            conn,
            "UPDATE player_world_devices SET last_seen_at = now() WHERE id = %s",
            (device["id"],),
        )
        execute(
            conn,
            """
            UPDATE player_world_connections
            SET status = %s, last_seen_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (status, device["player_world_connection_id"]),
        )
    return jsonify({"accepted": accepted, "duplicates": len(events) - accepted, "status": status})


def normalize_event(raw_event):
    if not isinstance(raw_event, dict):
        raise ValueError("Each event must be an object.")
    try:
        event_id = str(UUID(str(raw_event.get("event_id", ""))))
    except ValueError:
        raise ValueError("Each event requires a valid event_id.") from None
    event_type = str(raw_event.get("event_type", "")).strip()
    if event_type not in EVENT_PAYLOAD_FIELDS:
        raise ValueError("The event type is not allowed.")
    occurred_at = parse_occurred_at(raw_event.get("occurred_at"))
    payload = raw_event.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("Event payload must be an object.")
    if set(payload) - EVENT_PAYLOAD_FIELDS[event_type]:
        raise ValueError("The event payload contains fields that are not allowed.")
    normalized_payload = normalize_event_payload(payload)
    if len(json.dumps(normalized_payload, separators=(",", ":")).encode("utf-8")) > 2048:
        raise ValueError("The event payload is too large.")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "payload": normalized_payload,
    }


def normalize_event_payload(payload):
    normalized = {}
    if "world_label" in payload:
        world_label = normalize_short_text(payload["world_label"], 120)
        if not world_label:
            raise ValueError("World label must be non-empty when provided.")
        normalized["world_label"] = world_label
    if "server_fingerprint" in payload:
        fingerprint = str(payload["server_fingerprint"]).strip().lower()
        if not WORLD_FINGERPRINT.fullmatch(fingerprint):
            raise ValueError("Server fingerprint must be a SHA-256 value.")
        normalized["server_fingerprint"] = fingerprint
    if "connection_kind" in payload:
        connection_kind = str(payload["connection_kind"]).strip()
        if connection_kind not in {"multiplayer", "singleplayer"}:
            raise ValueError("Connection kind must be multiplayer or singleplayer.")
        normalized["connection_kind"] = connection_kind
    return normalized


def parse_occurred_at(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Each event requires occurred_at.")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("Event occurred_at must be an ISO-8601 timestamp.") from None
    if parsed.tzinfo is None:
        raise ValueError("Event occurred_at must include a timezone.")
    now = datetime.now(timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now + timedelta(minutes=5) or parsed < now - timedelta(days=7):
        raise ValueError("Event occurred_at is outside the accepted time window.")
    return parsed


def normalize_short_text(value, maximum):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        return None
    return value


def bearer_token():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token if 20 <= len(token) <= 200 else None


def new_prefixed_token(prefix):
    return prefix + secrets.token_urlsafe(32)


def store_pairing_token(conn, connection_id, user_id, token):
    execute(
        conn,
        """
        INSERT INTO player_world_pairing_tokens
            (player_world_connection_id, token_hash, created_by_user_id, expires_at)
        VALUES (%s, %s, %s, %s)
        """,
        (connection_id, hash_session_token(token), user_id, datetime.now(timezone.utc) + PAIRING_LIFETIME),
    )


def pairing_response(token):
    return {
        "token": token,
        "expires_in_seconds": int(PAIRING_LIFETIME.total_seconds()),
        "shown_once": True,
    }


def owned_connection(conn, connection_id, user_id):
    return fetch_one(
        conn,
        """
        SELECT id::text, community_id::text, owner_user_id::text, status
        FROM player_world_connections
        WHERE id = %s AND owner_user_id = %s
        """,
        (connection_id, user_id),
    )


def accessible_connection(conn, connection_id, user_id):
    return fetch_one(
        conn,
        """
        SELECT pwc.id::text, pwc.community_id::text, pwc.owner_user_id::text,
               pwc.status, cm.role
        FROM player_world_connections pwc
        JOIN community_memberships cm ON cm.community_id = pwc.community_id
        WHERE pwc.id = %s AND cm.user_id = %s
        """,
        (connection_id, user_id),
    )


def connection_response(row):
    response = {
        "id": row["id"],
        "community_id": row["community_id"],
        "owner_user_id": row["owner_user_id"],
        "display_name": row["display_name"],
        "game_type": row["game_type"],
        "source_kind": row["source_kind"],
        "status": effective_status(row["status"], row.get("last_seen_at")),
        "discord_sharing_enabled": row["discord_sharing_enabled"],
        "last_seen_at": row.get("last_seen_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "revoked_at": row.get("revoked_at"),
    }
    if row.get("owner_display_name"):
        response["owner_display_name"] = row["owner_display_name"]
    return response


def effective_status(status, last_seen_at):
    if status in {"ready", "in_world"} and last_seen_at:
        if last_seen_at < datetime.now(timezone.utc) - timedelta(minutes=3):
            return "offline"
    return status


def status_for_event(event_type):
    return {
        "client.started": "ready",
        "client.stopped": "offline",
        "world.joined": "in_world",
        "world.left": "ready",
        "heartbeat": "in_world",
    }[event_type]


def audit_connection(conn, user_id, community_id, action, connection_id, details=None):
    execute(
        conn,
        """
        INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, 'player_world_connection', %s, %s::jsonb)
        """,
        (user_id, community_id, action, connection_id, json.dumps(details or {}, separators=(",", ":"))),
    )
