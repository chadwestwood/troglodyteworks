import json
from datetime import datetime, timezone

from flask import Blueprint, current_app, g, jsonify, redirect, request

from ..auth import current_user_from_cookie, require_user, user_response
from ..db import execute, fetch_all, fetch_one
from ..oauth import (
    ExternalProfile,
    OAuthConfigurationError,
    OAuthProviderError,
    authorization_url,
    exchange_authorization_code,
    hash_oauth_value,
    new_oauth_state,
    new_pkce_verifier,
    safe_redirect_path,
)
from ..responses import api_error
from .auth import create_session, set_session_cookie

account_identities_bp = Blueprint("twe_account_identities", __name__)


@account_identities_bp.get("/auth/<provider>/start")
def start_oauth_login(provider):
    if provider not in {"google", "discord"}:
        return api_error("UNSUPPORTED_PROVIDER", "That authentication provider is not supported.", 404)
    return begin_oauth(provider, "login", user_id=None, redirect_path=request.args.get("next") or "/communities/", as_json=False)


@account_identities_bp.get("/auth/<provider>/callback")
def oauth_callback(provider):
    if provider not in {"google", "discord"}:
        return api_error("UNSUPPORTED_PROVIDER", "That authentication provider is not supported.", 404)
    error = request.args.get("error")
    if error:
        return api_error("OAUTH_PROVIDER_ERROR", "The provider did not authorize this request.", 400)
    state = request.args.get("state")
    code = request.args.get("code")
    if not state or not code:
        return api_error("OAUTH_CALLBACK_INVALID", "OAuth callback is missing required values.", 400)
    config = current_app.config["TWE_CONFIG"]
    with current_app.config["TWE_DB"].connect() as conn:
        pending_state = read_oauth_state(conn, state, provider)
        if not pending_state:
            return api_error("OAUTH_STATE_INVALID", "OAuth state was invalid or expired.", 400)
        if pending_state["purpose"] == "link":
            current = current_user_from_cookie()
            if not current or current["id"] != pending_state["user_id"]:
                return api_error(
                    "OAUTH_LINK_SESSION_CHANGED",
                    "Return to the same Troglodyte Works address where you started and try again.",
                    401,
                )
        oauth_state = consume_oauth_state(conn, state, provider)
        if not oauth_state:
            return api_error("OAUTH_STATE_INVALID", "OAuth state was invalid or expired.", 400)
        try:
            profile = exchange_authorization_code(
                provider,
                code,
                oauth_state["code_verifier"],
                config,
                nonce=oauth_state.get("nonce"),
            )
        except (OAuthConfigurationError, OAuthProviderError):
            return api_error("OAUTH_PROVIDER_ERROR", "OAuth provider verification failed.", 400)
        if profile.provider != provider:
            return api_error("OAUTH_PROVIDER_ERROR", "OAuth provider did not match the requested provider.", 400)
        if oauth_state["purpose"] == "link":
            return finish_link_callback(conn, oauth_state, profile)
        return finish_login_callback(conn, oauth_state, profile, config)


@account_identities_bp.get("/account/identities")
@require_user
def list_identities():
    config = current_app.config["TWE_CONFIG"]
    is_admin = g.current_user["email"].lower() in set(config.admin_emails)
    with current_app.config["TWE_DB"].connect() as conn:
        user = fetch_one(conn, "SELECT id::text, password_hash FROM users WHERE id = %s", (g.current_user["id"],))
        rows = fetch_all(
            conn,
            """
            SELECT provider, provider_subject, provider_username, provider_email,
                   provider_email_verified, linked_at, last_authenticated_at
            FROM user_external_identities
            WHERE user_id = %s
            ORDER BY provider
            """,
            (g.current_user["id"],),
        )
    providers = {row["provider"]: identity_response(row) for row in rows}
    google = providers.get("google") or disconnected_provider("google")
    discord = providers.get("discord") or disconnected_provider("discord")
    google["configured"] = bool(config.google_client_id and config.google_client_secret and config.google_redirect_uri)
    discord["configured"] = bool(config.discord_client_id and config.discord_client_secret and config.discord_redirect_uri)
    return jsonify(
        {
            "identities": {
                "local": {
                    "provider": "local",
                    "connected": bool(user and user["password_hash"]),
                    "can_unlink": False,
                    "configured": True,
                },
                "google": google,
                "discord": discord,
            },
            "admin": {"available": is_admin},
        }
    )


@account_identities_bp.post("/account/identities/<provider>/connect")
@require_user
def connect_identity(provider):
    if provider not in {"google", "discord"}:
        return api_error("UNSUPPORTED_PROVIDER", "That authentication provider is not supported.", 404)
    payload = request.get_json(silent=True) or {}
    redirect_path = payload.get("return_to") or "/account/"
    return begin_oauth(provider, "link", user_id=g.current_user["id"], redirect_path=redirect_path, as_json=True)


@account_identities_bp.delete("/account/identities/<provider>")
@require_user
def unlink_identity(provider):
    if provider not in {"google", "discord"}:
        return api_error("UNSUPPORTED_PROVIDER", "That authentication provider is not supported.", 404)
    with current_app.config["TWE_DB"].connect() as conn:
        remaining = usable_auth_method_count(conn, g.current_user["id"])
        identity = fetch_one(
            conn,
            "SELECT id::text FROM user_external_identities WHERE user_id = %s AND provider = %s",
            (g.current_user["id"], provider),
        )
        if not identity:
            return jsonify({"success": True})
        if remaining <= 1:
            return api_error("FINAL_AUTH_METHOD", "You cannot disconnect your final sign-in method.", 409)
        execute(conn, "DELETE FROM user_external_identities WHERE id = %s", (identity["id"],))
        if provider == "discord":
            execute(
                conn,
                "UPDATE discord_identities SET user_id = NULL, updated_at = now() WHERE user_id = %s",
                (g.current_user["id"],),
            )
        execute(
            conn,
            "INSERT INTO audit_logs (user_id, action, target_type, details) VALUES (%s, %s, 'user_external_identity', %s::jsonb)",
            (g.current_user["id"], f"account.identity.{provider}.unlink", json.dumps({"provider": provider})),
        )
    return jsonify({"success": True})


def begin_oauth(provider: str, purpose: str, user_id: str | None, redirect_path: str, as_json: bool):
    config = current_app.config["TWE_CONFIG"]
    state = new_oauth_state()
    code_verifier = new_pkce_verifier()
    nonce = new_oauth_state() if provider == "google" else None
    redirect_path = safe_redirect_path(redirect_path, default="/communities/" if purpose == "login" else "/account/")
    try:
        url = authorization_url(provider, config, state, code_verifier, nonce=nonce)
    except OAuthConfigurationError as exc:
        return api_error("OAUTH_NOT_CONFIGURED", str(exc), 503)
    with current_app.config["TWE_DB"].connect() as conn:
        execute(
            conn,
            """
            INSERT INTO oauth_states
                (state_hash, provider, purpose, user_id, redirect_path, code_verifier, nonce, nonce_hash, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now() + interval '10 minutes')
            """,
            (hash_oauth_value(state), provider, purpose, user_id, redirect_path, code_verifier, nonce, hash_oauth_value(nonce) if nonce else None),
        )
    if as_json:
        return jsonify({"oauth": {"authorization_url": url, "provider": provider, "purpose": purpose}})
    return redirect(url, code=302)


def consume_oauth_state(conn, state: str, provider: str):
    row = fetch_one(
        conn,
        """
        UPDATE oauth_states
        SET consumed_at = now()
        WHERE state_hash = %s
          AND provider = %s
          AND consumed_at IS NULL
          AND expires_at > now()
        RETURNING provider, purpose, user_id::text, redirect_path, code_verifier, nonce, nonce_hash
        """,
        (hash_oauth_value(state), provider),
    )
    return row


def read_oauth_state(conn, state: str, provider: str):
    return fetch_one(
        conn,
        """
        SELECT purpose, user_id::text
        FROM oauth_states
        WHERE state_hash = %s
          AND provider = %s
          AND consumed_at IS NULL
          AND expires_at > now()
        """,
        (hash_oauth_value(state), provider),
    )


def finish_login_callback(conn, oauth_state, profile: ExternalProfile, config):
    identity = fetch_one(
        conn,
        """
        SELECT u.id::text, u.email, u.display_name
        FROM user_external_identities uei
        JOIN users u ON u.id = uei.user_id
        WHERE uei.provider = %s AND uei.provider_subject = %s
        """,
        (profile.provider, profile.subject),
    )
    if identity:
        touch_external_identity(conn, identity["id"], profile)
        user = identity
    else:
        user = create_oauth_user(conn, profile)
        link_external_identity(conn, user["id"], profile)
    sync_discord_guild_authorities(conn, user["id"], profile)
    token = create_session(conn, user["id"], config)
    response = redirect(safe_redirect_path(oauth_state["redirect_path"]), code=302)
    set_session_cookie(response, token, config)
    return response


def finish_link_callback(conn, oauth_state, profile: ExternalProfile):
    current = current_user_from_cookie()
    if not current or current["id"] != oauth_state["user_id"]:
        return api_error("OAUTH_LINK_SESSION_CHANGED", "Sign in again before connecting this account.", 401)
    result = link_external_identity(conn, oauth_state["user_id"], profile)
    if result == "conflict":
        return api_error("EXTERNAL_IDENTITY_CONFLICT", "That provider account is already connected to another TWE user.", 409)
    sync_discord_guild_authorities(conn, oauth_state["user_id"], profile)
    response = redirect(safe_redirect_path(oauth_state["redirect_path"], default="/account/"), code=302)
    return response


def create_oauth_user(conn, profile: ExternalProfile):
    preferred_email = normalized_provider_email(profile)
    email = unique_oauth_email(conn, profile.provider, profile.subject, preferred_email)
    display_name = profile.username or (profile.email.split("@", 1)[0] if profile.email else f"{profile.provider.title()} User")
    user = fetch_one(
        conn,
        """
        INSERT INTO users (email, password_hash, display_name)
        VALUES (%s, NULL, %s)
        RETURNING id::text, email, display_name
        """,
        (email, display_name),
    )
    execute(
        conn,
        "INSERT INTO audit_logs (user_id, action, target_type, target_id) VALUES (%s, 'auth.oauth_register', 'user', %s)",
        (user["id"], user["id"]),
    )
    return user


def unique_oauth_email(conn, provider: str, subject: str, provider_email: str | None) -> str:
    if provider_email:
        existing = fetch_one(conn, "SELECT id::text FROM users WHERE lower(email) = %s", (provider_email,))
        if not existing:
            return provider_email
    suffix = hash_oauth_value(f"{provider}:{subject}")[:16]
    return f"{provider}-{suffix}@external.twe.invalid"


def normalized_provider_email(profile: ExternalProfile) -> str | None:
    if not profile.email:
        return None
    return profile.email.strip().lower()


def link_external_identity(conn, user_id: str, profile: ExternalProfile) -> str:
    existing = fetch_one(
        conn,
        """
        SELECT user_id::text
        FROM user_external_identities
        WHERE provider = %s AND provider_subject = %s
        """,
        (profile.provider, profile.subject),
    )
    if existing:
        if existing["user_id"] == user_id:
            touch_external_identity(conn, user_id, profile)
            sync_discord_identity(conn, user_id, profile)
            return "linked"
        return "conflict"
    execute(
        conn,
        """
        INSERT INTO user_external_identities
            (user_id, provider, provider_subject, provider_username, provider_email, provider_email_verified, linked_at, last_authenticated_at)
        VALUES (%s, %s, %s, %s, %s, %s, now(), now())
        """,
        (user_id, profile.provider, profile.subject, profile.username, normalized_provider_email(profile), profile.email_verified),
    )
    sync_discord_identity(conn, user_id, profile)
    execute(
        conn,
        "INSERT INTO audit_logs (user_id, action, target_type, details) VALUES (%s, %s, 'user_external_identity', %s::jsonb)",
        (user_id, f"account.identity.{profile.provider}.link", json.dumps({"provider": profile.provider})),
    )
    return "linked"


def touch_external_identity(conn, user_id: str, profile: ExternalProfile):
    execute(
        conn,
        """
        UPDATE user_external_identities
        SET provider_username = %s,
            provider_email = %s,
            provider_email_verified = %s,
            last_authenticated_at = now(),
            updated_at = now()
        WHERE provider = %s AND provider_subject = %s AND user_id = %s
        """,
        (profile.username, normalized_provider_email(profile), profile.email_verified, profile.provider, profile.subject, user_id),
    )


def sync_discord_identity(conn, user_id: str, profile: ExternalProfile):
    if profile.provider != "discord":
        return
    existing = fetch_one(
        conn,
        "SELECT user_id::text FROM discord_identities WHERE discord_user_id = %s",
        (profile.subject,),
    )
    if existing and existing["user_id"] and existing["user_id"] != user_id:
        return
    execute(
        conn,
        """
        INSERT INTO discord_identities (discord_user_id, user_id, linked_at)
        VALUES (%s, %s, now())
        ON CONFLICT (discord_user_id)
        DO UPDATE SET user_id = EXCLUDED.user_id, linked_at = COALESCE(discord_identities.linked_at, now()), updated_at = now()
        """,
        (profile.subject, user_id),
    )


def sync_discord_guild_authorities(conn, user_id: str, profile: ExternalProfile):
    if profile.provider != "discord":
        return
    execute(
        conn,
        "UPDATE discord_user_guild_memberships SET expires_at = now() WHERE user_id = %s",
        (user_id,),
    )
    for guild_id, guild_name in profile.guilds:
        execute(
            conn,
            """
            INSERT INTO discord_user_guild_memberships
                (user_id, discord_user_id, discord_guild_id, discord_guild_name, expires_at)
            VALUES (%s, %s, %s, %s, now() + interval '24 hours')
            ON CONFLICT (user_id, discord_guild_id)
            DO UPDATE SET discord_user_id = EXCLUDED.discord_user_id,
                          discord_guild_name = EXCLUDED.discord_guild_name,
                          verified_at = now(), expires_at = EXCLUDED.expires_at
            """,
            (user_id, profile.subject, guild_id, guild_name),
        )
    execute(
        conn,
        """
        UPDATE discord_guild_authority_verifications
        SET can_manage_guild = false, expires_at = now()
        WHERE user_id = %s
        """,
        (user_id,),
    )
    for guild_id, guild_name, authority_source in profile.managed_guilds:
        execute(
            conn,
            """
            INSERT INTO discord_guild_authority_verifications
                (user_id, discord_user_id, discord_guild_id, discord_guild_name,
                 can_manage_guild, authority_source, expires_at)
            VALUES (%s, %s, %s, %s, true, %s, now() + interval '1 hour')
            ON CONFLICT (user_id, discord_guild_id)
            DO UPDATE SET
                discord_user_id = EXCLUDED.discord_user_id,
                discord_guild_name = EXCLUDED.discord_guild_name,
                can_manage_guild = true,
                authority_source = EXCLUDED.authority_source,
                verified_at = now(),
                expires_at = EXCLUDED.expires_at
            """,
            (user_id, profile.subject, guild_id, guild_name, authority_source),
        )


def usable_auth_method_count(conn, user_id: str) -> int:
    local = fetch_one(conn, "SELECT password_hash IS NOT NULL AS connected FROM users WHERE id = %s", (user_id,))
    external = fetch_one(conn, "SELECT count(*) AS count FROM user_external_identities WHERE user_id = %s", (user_id,))
    return (1 if local and local["connected"] else 0) + int(external["count"])


def disconnected_provider(provider: str):
    return {"provider": provider, "connected": False, "can_unlink": False}


def identity_response(row):
    return {
        "provider": row["provider"],
        "connected": True,
        "provider_subject": row["provider_subject"],
        "provider_username": row["provider_username"],
        "provider_email": row["provider_email"],
        "provider_email_verified": row["provider_email_verified"],
        "linked_at": row["linked_at"],
        "last_authenticated_at": row["last_authenticated_at"],
        "can_unlink": True,
    }
