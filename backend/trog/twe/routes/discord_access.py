from datetime import datetime, timedelta, timezone
import secrets
from urllib.parse import urlencode

from flask import Blueprint, current_app, g, jsonify, redirect, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..discord_api import DiscordAPIError, exchange_guild_authorization, installed_bot_guild, managed_guild
from ..oauth import new_pkce_verifier, pkce_challenge
from ..responses import api_error

discord_access_bp = Blueprint("twe_discord_access", __name__)

READ_CAPABILITIES = frozenset(
    {
        "instance.status.read",
        "instance.players.count.read",
        "instance.players.names.read",
        "instance.mods.names.read",
    }
)


@discord_access_bp.get("/discord/managed-guilds")
@require_user
def list_managed_discord_guilds():
    with current_app.config["TWE_DB"].connect() as conn:
        identity = fetch_one(
            conn,
            "SELECT discord_user_id FROM discord_identities WHERE user_id = %s",
            (g.current_user["id"],),
        )
        rows = fetch_all(
            conn,
            """
            SELECT discord_guild_id, discord_guild_name, authority_source, verified_at, expires_at
            FROM discord_guild_authority_verifications
            WHERE user_id = %s
              AND can_manage_guild = true
              AND expires_at > now()
            ORDER BY lower(discord_guild_name), discord_guild_id
            """,
            (g.current_user["id"],),
        )
    return jsonify(
        {
            "discord_connected": bool(identity),
            "guilds": [
                {
                    "id": row["discord_guild_id"],
                    "name": row["discord_guild_name"] or "Discord server",
                    "authority_source": row["authority_source"],
                    "verified_at": row["verified_at"],
                    "expires_at": row["expires_at"],
                }
                for row in rows
            ],
            "refresh_required": bool(identity) and not rows,
        }
    )


@discord_access_bp.post("/discord/instance-access-requests")
@require_user
def create_instance_access_request():
    payload = request.get_json(silent=True) or {}
    provider_community_id = str(payload.get("provider_community_id", "")).strip()
    game_instance_id = str(payload.get("game_instance_id", "")).strip()
    requested = normalize_capabilities(payload.get("requested_capabilities") or list(READ_CAPABILITIES))
    channel_scope = str(payload.get("channel_scope") or "all").strip()
    channel_ids = normalize_snowflake_list(payload.get("allowed_channel_ids") or [])
    if channel_scope not in {"all", "allowlist"}:
        return api_error("VALIDATION_ERROR", "Channel scope must be all or allowlist.", 400)
    if not provider_community_id or not game_instance_id:
        return api_error("VALIDATION_ERROR", "Provider Community and Instance are required.", 400)
    if requested is None:
        return api_error("VALIDATION_ERROR", "Only read-only Discord capabilities may be requested.", 400)
    if channel_ids is None:
        return api_error("VALIDATION_ERROR", "Discord channel IDs must be numeric.", 400)
    if channel_scope == "allowlist" and not channel_ids:
        return api_error("VALIDATION_ERROR", "At least one channel is required for allowlist scope.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        if not membership_for_community(conn, g.current_user["id"], provider_community_id):
            return api_error("FORBIDDEN", "You must belong to the provider Community before requesting access.", 403)
        instance = resolve_provider_instance(conn, provider_community_id, game_instance_id)
        if not instance:
            return api_error("INSTANCE_NOT_FOUND", "The provider Community does not own that Instance.", 404)
        provider_role = membership_for_community(conn, g.current_user["id"], provider_community_id)["role"]
        self_approved = provider_role in {"owner", "admin"}
        grant = fetch_one(
            conn,
            """
            INSERT INTO discord_instance_access_grants
                (provider_community_id, game_server_id, game_instance_id, requested_by, status, channel_scope,
                 requested_channel_ids, provider_approved_by, provider_approved_at)
            VALUES (%s, %s, %s, %s, 'pending_discord_verification', %s, %s,
                    CASE WHEN %s THEN %s::uuid ELSE NULL END, CASE WHEN %s THEN now() ELSE NULL END)
            RETURNING id::text, status, channel_scope
            """,
            (
                provider_community_id,
                instance["game_server_id"],
                game_instance_id,
                g.current_user["id"],
                channel_scope,
                channel_ids,
                self_approved,
                g.current_user["id"],
                self_approved,
            ),
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
    config = current_app.config["TWE_CONFIG"]
    if not config.discord_client_id or not config.discord_install_redirect_uri:
        return api_error("DISCORD_OAUTH_NOT_CONFIGURED", "Discord guild authorization is not configured.", 503)
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        if grant["status"] in {"active", "denied", "revoked"}:
            return api_error("INVALID_REQUEST_STATE", "This request cannot continue Discord authorization.", 409)
        if purpose == "guild_verification":
            guild_id = numeric_text(payload.get("discord_guild_id"))
            if not guild_id:
                return api_error("VALIDATION_ERROR", "A Discord server ID is required.", 400)
        else:
            guild_id = grant["consumer_discord_guild_id"]
            if not guild_id or not grant["discord_approved_at"]:
                return api_error("DISCORD_VERIFICATION_REQUIRED", "Verify Discord server authority before installing Trog.", 409)
        state = secrets.token_urlsafe(32)
        code_verifier = new_pkce_verifier()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
        execute(
            conn,
            """
            INSERT INTO discord_oauth_states
                (state, user_id, grant_id, purpose, expires_at, code_verifier, discord_guild_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (state, g.current_user["id"], grant_id, purpose, expires_at, code_verifier, guild_id),
        )
    return jsonify(
        {
            "oauth": {
                "authorization_url": discord_authorization_url(state, code_verifier, purpose, guild_id),
                "purpose": purpose,
            }
        }
    )


@discord_access_bp.get("/discord/oauth/callback")
@require_user
def discord_oauth_callback():
    state = str(request.args.get("state") or "").strip()
    code = str(request.args.get("code") or "").strip()
    if request.args.get("error"):
        return discord_setup_redirect(error="Discord authorization was cancelled.")
    if not state or not code:
        return api_error("OAUTH_CALLBACK_INVALID", "Discord callback is missing required values.", 400)
    with current_app.config["TWE_DB"].connect() as conn:
        oauth_state = consume_oauth_state(conn, state, g.current_user["id"])
        if not oauth_state:
            return api_error("INVALID_OAUTH_STATE", "OAuth state is invalid or expired.", 400)
        grant_id = oauth_state["grant_id"]
        grant = grant_for_user(conn, grant_id, g.current_user["id"])
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        try:
            discord = exchange_guild_authorization(code, oauth_state["code_verifier"], current_app.config["TWE_CONFIG"])
        except DiscordAPIError:
            return discord_setup_redirect(grant_id, error="Discord could not verify this request. Please try again.")
        identity = fetch_one(
            conn,
            """
            SELECT user_id::text
            FROM discord_identities
            WHERE discord_user_id = %s AND user_id = %s
            """,
            (discord.user_id, g.current_user["id"]),
        )
        if not identity:
            return discord_setup_redirect(grant_id, error="Use the same Discord account that is connected to your TWE account.")
        managed = managed_guild(discord.guilds, oauth_state["discord_guild_id"])
        if not managed:
            return discord_setup_redirect(grant_id, error="Discord did not confirm that you manage the selected server.")
        guild, source = managed
        guild_id = str(guild["id"])
        guild_name = str(guild.get("name") or "Discord server")
        if oauth_state["purpose"] == "bot_install":
            if guild_id != grant["consumer_discord_guild_id"]:
                return discord_setup_redirect(grant_id, error="The installed Discord server did not match the approved request.")
            try:
                installed_bot_guild(guild_id, current_app.config["TWE_CONFIG"])
            except DiscordAPIError:
                return discord_setup_redirect(grant_id, error="Trog could not confirm its installation in that Discord server.")
            updated = finalize_bot_installation(conn, grant)
            audit(
                conn,
                g.current_user["id"],
                grant["provider_community_id"],
                "discord.bot.install",
                "discord_instance_access_grant",
                grant_id,
                {"discord_guild_id": guild_id, "verified_by_discord": True},
            )
            return discord_setup_redirect(grant_id, installed="1", status=updated["status"])
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
            (g.current_user["id"], discord.user_id, guild_id, guild_name, source, datetime.now(timezone.utc) + timedelta(hours=1)),
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
            (discord.user_id, guild_id, guild_name, g.current_user["id"], discord.user_id, grant_id),
        )
        audit(
            conn,
            g.current_user["id"],
            grant["provider_community_id"],
            "discord.guild.verify",
            "discord_instance_access_grant",
            grant_id,
            {"discord_guild_id": guild_id, "authority_source": source, "verified_by_discord": True},
        )
    return discord_setup_redirect(grant_id, verified="1", status=updated["status"])


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
        if grant["status"] in {"denied", "revoked"}:
            return api_error("INVALID_REQUEST_STATE", "A denied or revoked request cannot be approved.", 409)
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


@discord_access_bp.post("/discord/instance-access-requests/<grant_id>/provider-denial")
@require_user
def deny_instance_access_request(grant_id):
    with current_app.config["TWE_DB"].connect() as conn:
        grant = grant_by_id(conn, grant_id)
        if not grant:
            return api_error("NOT_FOUND", "Instance access request was not found.", 404)
        if not provider_manager(conn, g.current_user["id"], grant["provider_community_id"]):
            return api_error("FORBIDDEN", "Only a provider owner or admin may deny this request.", 403)
        if grant["status"] in {"active", "revoked"}:
            return api_error("INVALID_REQUEST_STATE", "Active access must be revoked instead of denied.", 409)
        updated = fetch_one(
            conn,
            """
            UPDATE discord_instance_access_grants
            SET status = 'denied', denied_by = %s, denied_at = now(), updated_at = now()
            WHERE id = %s
            RETURNING id::text, status
            """,
            (g.current_user["id"], grant_id),
        )
        audit(
            conn,
            g.current_user["id"],
            grant["provider_community_id"],
            "discord.instance_access.deny",
            "discord_instance_access_grant",
            grant_id,
            {},
        )
    return jsonify({"request": request_response(updated)})


def finalize_bot_installation(conn, grant):
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
    for channel_id in grant["requested_channel_ids"]:
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
    return fetch_one(
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
        (installation["id"], grant["id"]),
    )


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
                diag.provider_community_id::text,
                c.name AS provider_community_name,
                gi.name AS instance_name,
                diag.channel_scope,
                diag.requested_channel_ids,
                diag.requested_by::text,
                diag.discord_approved_at,
                diag.provider_approved_at,
                diag.installed_at,
                (diag.requested_by = %s) AS is_requester,
                (cm.role IN ('owner', 'admin')) AS can_manage_provider,
                ARRAY(
                    SELECT capability
                    FROM discord_instance_access_grant_capabilities cap
                    WHERE cap.discord_instance_access_grant_id = diag.id
                      AND cap.revoked_at IS NULL
                    ORDER BY capability
                ) AS capabilities,
                diag.created_at,
                diag.activated_at,
                diag.revoked_at
            FROM discord_instance_access_grants diag
            JOIN communities c ON c.id = diag.provider_community_id
            JOIN game_instances gi ON gi.id = diag.game_instance_id
            JOIN community_memberships cm ON cm.community_id = diag.provider_community_id
            WHERE diag.requested_by = %s
               OR (cm.user_id = %s AND cm.role IN ('owner', 'admin'))
            ORDER BY diag.created_at DESC
            """,
            (g.current_user["id"], g.current_user["id"], g.current_user["id"]),
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
            requested_channel_ids,
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
    if grant["requested_by"] == user_id or provider_manager(conn, user_id, grant["provider_community_id"]):
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


def consume_oauth_state(conn, state: str, user_id: str):
    row = fetch_one(
        conn,
        """
        UPDATE discord_oauth_states
        SET consumed_at = now()
        WHERE state = %s
          AND user_id = %s
          AND consumed_at IS NULL
          AND expires_at > now()
        RETURNING state, grant_id::text, purpose, code_verifier, discord_guild_id
        """,
        (state, user_id),
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


def normalize_snowflake_list(values):
    if not isinstance(values, list):
        return None
    normalized = []
    for value in values:
        snowflake = numeric_text(value)
        if not snowflake:
            return None
        if snowflake not in normalized:
            normalized.append(snowflake)
    return normalized


def discord_authorization_url(state: str, code_verifier: str, purpose: str, guild_id: str):
    config = current_app.config["TWE_CONFIG"]
    scope = "identify guilds"
    if purpose == "bot_install":
        scope = "identify guilds bot applications.commands"
    params = {
        "client_id": config.discord_client_id,
        "redirect_uri": config.discord_install_redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "code_challenge": pkce_challenge(code_verifier),
        "code_challenge_method": "S256",
    }
    if purpose == "bot_install":
        params["guild_id"] = guild_id
        params["disable_guild_select"] = "true"
        if config.discord_bot_permissions is not None:
            params["permissions"] = str(config.discord_bot_permissions)
    return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"


def discord_setup_redirect(grant_id: str | None = None, **values):
    if "error" in values:
        values["discord_error"] = values.pop("error")
    params = {key: value for key, value in values.items() if value is not None}
    if grant_id:
        params["request"] = grant_id
    suffix = f"?{urlencode(params)}" if params else ""
    return redirect(f"/discord/request-access/{suffix}", code=302)


def audit(conn, user_id, community_id, action, target_type, target_id, details):
    execute(
        conn,
        """
        INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (user_id, community_id, action, target_type, target_id, __import__("json").dumps(details)),
    )
