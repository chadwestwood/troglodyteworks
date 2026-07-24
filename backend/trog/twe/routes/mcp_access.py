import json
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..security import hash_session_token, new_session_token
from ..serializers import iso

mcp_access_bp = Blueprint("twe_mcp_access", __name__)


def require_browser_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.headers.get("X-TWE-CSRF") != "1":
            return api_error("CSRF_REJECTED", "The browser request could not be verified.", 403)
        return view(*args, **kwargs)

    return wrapped


@mcp_access_bp.get("/account/mcp-tokens")
@require_user
def list_mcp_tokens():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT id::text, name, token_prefix, created_at, expires_at,
                   last_used_at, revoked_at
            FROM mcp_access_tokens
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (g.current_user["id"],),
        )
    return jsonify({"tokens": [_token_response(row) for row in rows]})


@mcp_access_bp.post("/account/mcp-tokens")
@require_user
@require_browser_csrf
def create_mcp_token():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "TWE MCP client")
    expires_days = payload.get("expires_days", 90)
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        return api_error("VALIDATION_ERROR", "Token name must be between 1 and 80 characters.", 400)
    if not isinstance(expires_days, int) or not 1 <= expires_days <= 365:
        return api_error("VALIDATION_ERROR", "Token lifetime must be between 1 and 365 days.", 400)

    raw_token = f"twe_mcp_{new_session_token()}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
    with current_app.config["TWE_DB"].connect() as conn:
        row = fetch_one(
            conn,
            """
            INSERT INTO mcp_access_tokens
                (user_id, name, token_hash, token_prefix, expires_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id::text, name, token_prefix, created_at, expires_at,
                      last_used_at, revoked_at
            """,
            (
                g.current_user["id"],
                name.strip(),
                hash_session_token(raw_token),
                raw_token[:16],
                expires_at,
            ),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs
                (user_id, action, target_type, target_id, details)
            VALUES (%s, 'mcp.token.created', 'mcp_access_token', %s, %s::jsonb)
            """,
            (
                g.current_user["id"],
                row["id"],
                json.dumps({"name": name.strip(), "expires_at": iso(expires_at)}),
            ),
        )
    response = _token_response(row)
    response["token"] = raw_token
    response["token_notice"] = "Copy this token now. Troglodyte Works will not show it again."
    return jsonify({"mcp_token": response}), 201


@mcp_access_bp.delete("/account/mcp-tokens/<token_id>")
@require_user
@require_browser_csrf
def revoke_mcp_token(token_id):
    with current_app.config["TWE_DB"].connect() as conn:
        row = fetch_one(
            conn,
            """
            UPDATE mcp_access_tokens
            SET revoked_at = COALESCE(revoked_at, now())
            WHERE id = %s AND user_id = %s
            RETURNING id::text, name
            """,
            (token_id, g.current_user["id"]),
        )
        if not row:
            return api_error("NOT_FOUND", "MCP token was not found.", 404)
        execute(
            conn,
            """
            INSERT INTO audit_logs
                (user_id, action, target_type, target_id, details)
            VALUES (%s, 'mcp.token.revoked', 'mcp_access_token', %s, %s::jsonb)
            """,
            (g.current_user["id"], row["id"], json.dumps({"name": row["name"]})),
        )
    return jsonify({"success": True})


def _token_response(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "token_prefix": row["token_prefix"],
        "created_at": iso(row["created_at"]),
        "expires_at": iso(row["expires_at"]),
        "last_used_at": iso(row["last_used_at"]),
        "revoked_at": iso(row["revoked_at"]),
        "active": row["revoked_at"] is None
        and (row["expires_at"] is None or row["expires_at"] > datetime.now(timezone.utc)),
    }
