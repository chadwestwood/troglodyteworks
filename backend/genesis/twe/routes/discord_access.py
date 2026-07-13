from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import urlencode

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error

discord_access_bp = Blueprint("twe_discord_access", __name__)

READ_CAPABILITIES = frozenset(
    {
        "instance.status.read",
        "instance.players.count.read",
        "instance.players.names.read",
    }
)
MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8


@discord_access_bp.post("/discord/identity/link")
@require_user
def link_discord_identity():
    payload = request.get_json(silent=True) or {}
    discord_user_id = numeric_text(payload.get("discord_user_id"))
    if not discord_user_id:
        return api_error("VALIDATION_ERROR", "A Discord user ID is required.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        existing = fetch_one(
            conn,
            """
            SELECT user_id::text
            FROM discord_identities
            WHERE discord_user_id = %s
            """,
            (discord_user_id,),
        )
        if existing and existing["user_id"] and existing["user_id"] != g.current_user["id"]:
            return api_error("DISCORD_IDENTITY_LINKED", "That Discord identity is already linked.", 409)
        fetch_one(
            conn,
            """
            INSERT INTO discord_identities (discord_user_id, user_id, linked_at)
            VALUES (%s, %s, now())
            ON CONFLICT (discord_user_id)
            DO UPDATE SET user_id = EXCLUDED.user_id, linked_at = now(), updated_at = now()
            RETURNING id
            """,
            (discord_user_id, g.current_user["id"]),
        )
        audit(conn, g.current_user["id"], None, "discord.identity.link", "discord_identity", None, {"discord_user_id": discord_user_id})

    return jsonify({"discord_identity": {"discord_user_id": discord_user_id, "linked": True}})


@discord_access_bp.post("/discord/instance-access-requests")
@require_user
def create_instance_access_request():
    payload = request.get_json(silent=True) or {}
    provider_community_id = str(payload.get("provider_community_id", "")).strip()
    game_instance_id = str(payload.get("game_instance_id", "")).strip()
    requested = normalize_capabilities(payload.get("requested_capabilities") or list(READ_CAPABILITIES))
    channel_scope = str(payload.get("channel_scope") or "all").strip()
    if channel_scope not in {"all", "allowlist"}:
        return api_error("VALIDATION_ERROR", "Channel scope must be all or allowlist.", 400)
    if not provider_community_id or not game_instance_id:
        return api_error("VALIDATION_ERROR", "Provider Community and Instance are required.", 400)
    if requested is None:
        return api_error("VALIDATION_ERROR", "Only read-only Discord capabilities may be requested.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        if not membership_for_community(conn, g.current_user["id"], provider_community_id):
            return api_error("FORBIDDEN", "You must belong to the provider Community before requesting access.", 403)
        instance = resolve_provider_instance(conn, provider_community_id, game_instance_id)
        if not instance:
            return api_error("INSTANCE_NOT_FOUND", "The provider Community does not own that Instance.", 404)
        grant = fetch_one(
            conn,
            """
            INSERT INTO discord_instance_access_grants
                (provider_community_id, game_server_id, game_instance_id, requested_by, status, channel_scope)
            VALUES (%s, %s, %s, %s, 'pending_discord_verification', %s)
            RETURNING id::text, status, channel_scope
            """,
            (provider_community_id, instance["game_server_id"], game_instance_id, g.current_user["id"], channel_scope),
        )
        for capability in requested:
            execute(
                conn,
                """
                INSERT INTO discord_instance_access_grant_capabilities
                    (discord_instance_access_grant_id, capability)
                VALUES (%s, %s)
                """,
                (grant["id"], capability),
            )
        audit(
            conn,
            g.current_user["id"],
            provider_community_id,
            "discord.instance_access.request",
            "discord_instance_access_grant",
            grant["id"],
            {"game_instance_id": game_instance_id, "requested_capabilities": requested},
        )

    return jsonify({"request": request_response(grant)}), 201


@discord_access_bp.get("/discord/instance-access-requests/<grant_id>")
@require_user
def get_instance_access_request(grant_id):
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        grant["capabilities"] = grant_capabilities(conn, grant_id)
        grant["channels"] = grant_channels(conn, grant["discord_guild_installation_id"])
    return jsonify({"request": grant})


@discord_access_bp.post("/discord/instance-access-requests/<grant_id>/oauth-state")
@require_user
def create_oauth_state(grant_id):
    payload = request.get_json(silent=True) or {}
    purpose = str(payload.get("purpose") or "guild_verification").strip()
    if purpose not in {"guild_verification", "bot_install"}:
        return api_error("VALIDATION_ERROR", "Unsupported OAuth purpose.", 400)
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        state = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        execute(
            conn,
            """
            INSERT INTO discord_oauth_states (state, user_id, grant_id, purpose, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (state, g.current_user["id"], grant_id, purpose, expires_at),
        )
    return jsonify({"oauth": {"state": state, "authorization_url": discord_authorization_url(state, purpose)}})


@discord_access_bp.post("/discord/instance-access-requests/<grant_id>/discord-verification")
@require_user
def verify_discord_guild_authority(grant_id):
    payload = request.get_json(silent=True) or {}
    state = str(payload.get("state") or "").strip()
    discord_user_id = numeric_text(payload.get("discord_user_id"))
    guild_id = numeric_text(payload.get("discord_guild_id"))
    guild_name = str(payload.get("discord_guild_name") or "").strip() or None
    owner = bool(payload.get("owner"))
    permissions = parse_permissions(payload.get("permissions"))
    if not state or not discord_user_id or not guild_id or permissions is None:
        return api_error("VALIDATION_ERROR", "OAuth state, Discord user, guild, and permissions are required.", 400)

    can_manage, source = guild_authority(owner, permissions)
    if not can_manage:
        return api_error("DISCORD_GUILD_AUTHORITY_REQUIRED", "Discord owner, Administrator, or Manage Guild authority is required.", 403)

    with current_app.config["TWE_DB"].connect() as conn:
        oauth_state = consume_oauth_state(conn, state, g.current_user["id"], grant_id, "guild_verification")
        if not oauth_state:
            return api_error("INVALID_OAUTH_STATE", "OAuth state is invalid or expired.", 400)
        identity = fetch_one(
            conn,
            """
            SELECT user_id::text
            FROM discord_identities
            WHERE discord_user_id = %s AND user_id = %s
            """,
            (discord_user_id, g.current_user["id"]),
        )
        if not identity:
            return api_error("DISCORD_IDENTITY_NOT_LINKED", "Link this Discord identity to your TWE account first.", 403)
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        fetch_one(
            conn,
            """
            INSERT INTO discord_guild_authority_verifications
                (user_id, discord_user_id, discord_guild_id, discord_guild_name, can_manage_guild, authority_source, expires_at)
            VALUES (%s, %s, %s, %s, true, %s, %s)
            ON CONFLICT (user_id, discord_guild_id)
            DO UPDATE SET
                discord_user_id = EXCLUDED.discord_user_id,
                discord_guild_name = EXCLUDED.discord_guild_name,
                can_manage_guild = true,
                authority_source = EXCLUDED.authority_source,
                verified_at = now(),
                expires_at = EXCLUDED.expires_at
            RETURNING id
            """,
            (g.current_user["id"], discord_user_id, guild_id, guild_name, source, datetime.now(timezone.utc) + timedelta(hours=1)),
        )
        updated = fetch_one(
            conn,
            """
            UPDATE discord_instance_access_grants
            SET requester_discord_user_id = %s,
                consumer_discord_guild_id = %s,
                consumer_discord_guild_name = %s,
                discord_approved_by = %s,
                discord_approver_user_id = %s,
                discord_approved_at = now(),
                status = CASE
                    WHEN provider_approved_at IS NULL THEN 'pending_provider_approval'
                    WHEN discord_guild_installation_id IS NULL THEN 'pending_bot_installation'
                    ELSE status
                END,
                updated_at = now()
            WHERE id = %s
            RETURNING id::text, status
            """,
            (discord_user_id, guild_id, guild_name, g.current_user["id"], discord_user_id, grant_id),
        )
        audit(conn, g.current_user["id"], grant["provider_community_id"], "discord.guild.verify", "discord_instance_access_grant", grant_id, {"discord_guild_id": guild_id, "authority_source": source})

    return jsonify({"request": request_response(updated)})


@discord_access_bp.post("/discord/instance-access-requests/<grant_id>/provider-approval")
@require_user
def approve_instance_access_request(grant_id):
    payload = request.get_json(silent=True) or {}
    capabilities = normalize_capabilities(payload.get("approved_capabilities") or list(READ_CAPABILITIES))
    channel_scope = str(payload.get("channel_scope") or "").strip()
    if capabilities is None:
        return api_error("VALIDATION_ERROR", "Only read-only Discord capabilities may be approved.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_by_id(conn, grant_id)
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        if not provider_manager(conn, g.current_user["id"], grant["provider_community_id"]):
            return api_error("FORBIDDEN", "Only a provider owner or admin may approve this request.", 403)
        if not resolve_provider_instance(conn, grant["provider_community_id"], grant["game_instance_id"]):
            return api_error("INSTANCE_NOT_FOUND", "The provider Community does not own that Instance.", 404)
        execute(
            conn,
            """
            UPDATE discord_instance_access_grant_capabilities
            SET revoked_at = now()
            WHERE discord_instance_access_grant_id = %s AND revoked_at IS NULL
            """,
            (grant_id,),
        )
        for capability in capabilities:
            execute(
                conn,
                """
                INSERT INTO discord_instance_access_grant_capabilities
                    (discord_instance_access_grant_id, capability, granted_by)
                VALUES (%s, %s, %s)
                """,
                (grant_id, capability, g.current_user["id"]),
            )
        if channel_scope not in {"all", "allowlist"}:
            channel_scope = grant["channel_scope"]
        updated = fetch_one(
            conn,
            """
            UPDATE discord_instance_access_grants
            SET provider_approved_by = %s,
                provider_approved_at = now(),
                channel_scope = %s,
                status = CASE
                    WHEN discord_approved_at IS NULL THEN 'pending_discord_verification'
                    WHEN discord_guild_installation_id IS NULL THEN 'pending_bot_installation'
                    ELSE 'active'
                END,
                activated_at = CASE
                    WHEN discord_approved_at IS NOT NULL AND discord_guild_installation_id IS NOT NULL THEN now()
                    ELSE activated_at
                END,
                updated_at = now()
            WHERE id = %s
            RETURNING id::text, status, channel_scope
            """,
            (g.current_user["id"], channel_scope, grant_id),
        )
        audit(conn, g.current_user["id"], grant["provider_community_id"], "discord.instance_access.approve", "discord_instance_access_grant", grant_id, {"approved_capabilities": capabilities})

    return jsonify({"request": request_response(updated)})


@discord_access_bp.post("/discord/instance-access-requests/<grant_id>/bot-installation")
@require_user
def complete_bot_installation(grant_id):
    payload = request.get_json(silent=True) or {}
    channel_ids = [value for value in (numeric_text(item) for item in payload.get("allowed_channel_ids") or []) if value]
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        if not grant["consumer_discord_guild_id"] or not grant["discord_approved_at"]:
            return api_error("DISCORD_VERIFICATION_REQUIRED", "Discord guild verification is required before installation.", 409)
        verification = fetch_one(
            conn,
            """
            SELECT id::text
            FROM discord_guild_authority_verifications
            WHERE user_id = %s
              AND discord_guild_id = %s
              AND expires_at > now()
              AND can_manage_guild = true
            """,
            (g.current_user["id"], grant["consumer_discord_guild_id"]),
        )
        if not verification:
            return api_error("DISCORD_GUILD_AUTHORITY_REQUIRED", "Discord guild authority must be verified before installation.", 403)
        installation = fetch_one(
            conn,
            """
            INSERT INTO discord_guild_installations
                (discord_guild_id, community_id, game_server_id, installed_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (discord_guild_id)
            DO UPDATE SET
                community_id = EXCLUDED.community_id,
                game_server_id = EXCLUDED.game_server_id,
                installed_by = EXCLUDED.installed_by,
                updated_at = now()
            RETURNING id::text
            """,
            (grant["consumer_discord_guild_id"], grant["provider_community_id"], grant["game_server_id"], g.current_user["id"]),
        )
        execute(conn, "DELETE FROM discord_channel_policies WHERE discord_guild_installation_id = %s AND capability_category = 'read'", (installation["id"],))
        for channel_id in channel_ids:
            execute(
                conn,
                """
                INSERT INTO discord_channel_policies
                    (discord_guild_installation_id, discord_channel_id, capability_category, enabled)
                VALUES (%s, %s, 'read', true)
                ON CONFLICT (discord_guild_installation_id, discord_channel_id, capability_category)
                DO UPDATE SET enabled = true, updated_at = now()
                """,
                (installation["id"], channel_id),
            )
        updated = fetch_one(
            conn,
            """
            UPDATE discord_instance_access_grants
            SET discord_guild_installation_id = %s,
                installed_at = now(),
                status = CASE
                    WHEN provider_approved_at IS NOT NULL AND discord_approved_at IS NOT NULL THEN 'active'
                    ELSE 'pending_provider_approval'
                END,
                activated_at = CASE
                    WHEN provider_approved_at IS NOT NULL AND discord_approved_at IS NOT NULL THEN now()
                    ELSE activated_at
                END,
                updated_at = now()
            WHERE id = %s
            RETURNING id::text, status
            """,
            (installation["id"], grant_id),
        )
        audit(conn, g.current_user["id"], grant["provider_community_id"], "discord.bot.install", "discord_instance_access_grant", grant_id, {"discord_guild_id": grant["consumer_discord_guild_id"], "allowed_channel_ids": channel_ids})

    return jsonify({"request": request_response(updated)})


@discord_access_bp.post("/discord/instance-access-grants/<grant_id>/revoke")
@require_user
def revoke_instance_access_grant(grant_id):
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_by_id(conn, grant_id)
        if not grant:
            return api_error("NOT_FOUND", "Instance access grant was not found.", 404)
        if not provider_manager(conn, g.current_user["id"], grant["provider_community_id"]):
            return api_error("FORBIDDEN", "Only a provider owner or admin may revoke this grant.", 403)
        updated = fetch_one(
            conn,
            """
            UPDATE discord_instance_access_grants
            SET status = 'revoked', revoked_by = %s, revoked_at = now(), updated_at = now()
            WHERE id = %s
            RETURNING id::text, status
            """,
            (g.current_user["id"], grant_id),
        )
        audit(conn, g.current_user["id"], grant["provider_community_id"], "discord.instance_access.revoke", "discord_instance_access_grant", grant_id, {})
    return jsonify({"request": request_response(updated)})


@discord_access_bp.get("/discord/installations")
@require_user
def list_discord_installations():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT
                diag.id::text,
                diag.status,
                diag.consumer_discord_guild_id,
                diag.consumer_discord_guild_name,
                c.name AS provider_community_name,
                gi.name AS instance_name,
                diag.created_at,
                diag.activated_at,
                diag.revoked_at
            FROM discord_instance_access_grants diag
            JOIN communities c ON c.id = diag.provider_community_id
            JOIN game_instances gi ON gi.id = diag.game_instance_id
            JOIN community_memberships cm ON cm.community_id = diag.provider_community_id
            WHERE cm.user_id = %s OR diag.requested_by = %s
            ORDER BY diag.created_at DESC
            """,
            (g.current_user["id"], g.current_user["id"]),
        )
    return jsonify({"installations": rows})


def resolve_provider_instance(conn, provider_community_id: str, game_instance_id: str):
    return fetch_one(
        conn,
        """
        SELECT gi.id::text AS game_instance_id, gs.id::text AS game_server_id
        FROM game_instances gi
        JOIN game_servers gs ON gs.id = gi.game_server_id
        WHERE gi.id = %s
          AND gs.community_id = %s
        """,
        (game_instance_id, provider_community_id),
    )


def provider_manager(conn, user_id: str, provider_community_id: str) -> bool:
    membership = membership_for_community(conn, user_id, provider_community_id)
    return bool(membership and membership["role"] in {"owner", "admin"})


def grant_by_id(conn, grant_id: str):
    return fetch_one(
        conn,
        """
        SELECT
            id::text,
            discord_guild_installation_id::text,
            provider_community_id::text,
            game_server_id::text,
            game_instance_id::text,
            requested_by::text,
            consumer_discord_guild_id,
            consumer_discord_guild_name,
            status,
            channel_scope,
            provider_approved_at,
            discord_approved_at
        FROM discord_instance_access_grants
        WHERE id = %s
        """,
        (grant_id,),
    )


def grant_for_user(conn, grant_id: str, user_id: str):
    grant = grant_by_id(conn, grant_id)
    if not grant:
        return None
    if grant["requested_by"] == user_id or membership_for_community(conn, user_id, grant["provider_community_id"]):
        return grant
    return None


def grant_capabilities(conn, grant_id: str):
    rows = fetch_all(
        conn,
        """
        SELECT capability
        FROM discord_instance_access_grant_capabilities
        WHERE discord_instance_access_grant_id = %s AND revoked_at IS NULL
        ORDER BY capability
        """,
        (grant_id,),
    )
    return [row["capability"] for row in rows]


def grant_channels(conn, installation_id: str | None):
    if not installation_id:
        return []
    rows = fetch_all(
        conn,
        """
        SELECT discord_channel_id, capability_category, enabled
        FROM discord_channel_policies
        WHERE discord_guild_installation_id = %s
        ORDER BY discord_channel_id, capability_category
        """,
        (installation_id,),
    )
    return rows


def consume_oauth_state(conn, state: str, user_id: str, grant_id: str, purpose: str):
    row = fetch_one(
        conn,
        """
        UPDATE discord_oauth_states
        SET consumed_at = now()
        WHERE state = %s
          AND user_id = %s
          AND grant_id = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at > now()
        RETURNING state
        """,
        (state, user_id, grant_id, purpose),
    )
    return row


def request_response(row):
    return {key: value for key, value in row.items()}


def normalize_capabilities(values):
    if not isinstance(values, list) or not values:
        return None
    capabilities = sorted({str(value).strip() for value in values})
    if not capabilities or any(capability not in READ_CAPABILITIES for capability in capabilities):
        return None
    return capabilities


def numeric_text(value):
    text = str(value or "").strip()
    if not text or not text.isdigit() or len(text) > 20:
        return None
    return text


def parse_permissions(value):
    try:
        permissions = int(str(value))
    except (TypeError, ValueError):
        return None
    if permissions < 0:
        return None
    return permissions


def guild_authority(owner: bool, permissions: int):
    if owner:
        return True, "owner"
    if permissions & ADMINISTRATOR:
        return True, "administrator"
    if permissions & MANAGE_GUILD:
        return True, "manage_guild"
    return False, None


def discord_authorization_url(state: str, purpose: str):
    config = current_app.config["TWE_CONFIG"]
    client_id = getattr(config, "discord_client_id", None)
    redirect_uri = getattr(config, "discord_redirect_uri", None)
    if not client_id or not redirect_uri:
        return None
    scope = "identify guilds"
    if purpose == "bot_install":
        scope = "identify guilds bot applications.commands"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    permissions = getattr(config, "discord_bot_permissions", None)
    if purpose == "bot_install" and permissions is not None:
        params["permissions"] = str(permissions)
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"


def audit(conn, user_id, community_id, action, target_type, target_id, details):
    execute(
        conn,
        """
        INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (user_id, community_id, action, target_type, target_id, __import__("json").dumps(details)),
    )
