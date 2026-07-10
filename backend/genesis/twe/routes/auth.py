from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

from ..auth import current_user_from_cookie, user_response
from ..db import execute, fetch_one
from ..responses import api_error
from ..security import hash_session_token, new_session_token, verify_password

auth_bp = Blueprint("twe_auth", __name__)


@auth_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    if not email or not isinstance(password, str):
        return api_error("VALIDATION_ERROR", "Email and password are required.", 400)

    config = current_app.config["TWE_CONFIG"]
    with current_app.config["TWE_DB"].connect() as conn:
        user = fetch_one(
            conn,
            "SELECT id::text, email, display_name, password_hash FROM users WHERE lower(email) = %s",
            (email,),
        )
        if not user or not verify_password(user["password_hash"], password):
            return api_error("INVALID_CREDENTIALS", "Invalid email or password.", 401)

        token = new_session_token()
        expires_at = datetime.now(timezone.utc) + config.session_lifetime
        execute(
            conn,
            """
            INSERT INTO sessions (user_id, session_token_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user["id"], hash_session_token(token), expires_at),
        )

    response = jsonify({"user": user_response(user)})
    response.set_cookie(
        config.session_cookie_name,
        token,
        httponly=True,
        secure=config.cookie_secure,
        samesite="Lax",
        max_age=int(config.session_lifetime.total_seconds()),
    )
    return response


@auth_bp.post("/auth/logout")
def logout():
    config = current_app.config["TWE_CONFIG"]
    token = request.cookies.get(config.session_cookie_name)
    if token:
        with current_app.config["TWE_DB"].connect() as conn:
            execute(
                conn,
                "UPDATE sessions SET revoked_at = %s WHERE session_token_hash = %s AND revoked_at IS NULL",
                (datetime.now(timezone.utc), hash_session_token(token)),
            )
    response = jsonify({"success": True})
    response.delete_cookie(config.session_cookie_name, samesite="Lax")
    return response


@auth_bp.get("/auth/me")
def me():
    user = current_user_from_cookie()
    if not user:
        return api_error("UNAUTHENTICATED", "Authentication is required.", 401)
    return jsonify({"user": user_response(user)})
