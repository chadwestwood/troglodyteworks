from datetime import datetime, timezone
import re

from flask import Blueprint, current_app, jsonify, request

from ..auth import current_user_from_cookie, user_response
from ..db import execute, fetch_one
from ..responses import api_error
from ..security import hash_password, hash_session_token, new_session_token, verify_password

auth_bp = Blueprint("twe_auth", __name__)

REGISTRATION_FIELDS = {"display_name", "email", "password", "password_confirmation"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


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

        token = create_session(conn, user["id"], config)

    response = jsonify({"user": user_response(user)})
    set_session_cookie(response, token, config)
    return response


@auth_bp.post("/auth/register")
def register():
    if current_user_from_cookie():
        return api_error("FORBIDDEN", "Sign out before creating another account.", 403)

    payload = request.get_json(silent=True) or {}
    validation_error = validate_registration_payload(payload)
    if validation_error:
        return validation_error

    email = normalize_email(payload["email"])
    display_name = str(payload["display_name"]).strip()
    config = current_app.config["TWE_CONFIG"]
    with current_app.config["TWE_DB"].connect() as conn:
        existing = fetch_one(conn, "SELECT id::text FROM users WHERE lower(email) = %s", (email,))
        if existing:
            return api_error("EMAIL_ALREADY_REGISTERED", "An account already exists for that email address.", 409)

        user = fetch_one(
            conn,
            """
            INSERT INTO users (email, password_hash, display_name)
            VALUES (%s, %s, %s)
            RETURNING id::text, email, display_name
            """,
            (email, hash_password(payload["password"]), display_name),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id, action, target_type, target_id)
            VALUES (%s, 'auth.register', 'user', %s)
            """,
            (user["id"], user["id"]),
        )
        token = create_session(conn, user["id"], config)

    response = jsonify({"user": user_response(user)})
    set_session_cookie(response, token, config)
    return response, 201


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


def validate_registration_payload(payload):
    if not isinstance(payload, dict):
        return api_error("VALIDATION_ERROR", "A JSON request body is required.", 400)
    unsupported = set(payload) - REGISTRATION_FIELDS
    if unsupported:
        return api_error("VALIDATION_ERROR", "Unsupported registration fields were provided.", 400)

    display_name = str(payload.get("display_name", "")).strip()
    email = normalize_email(payload.get("email", ""))
    password = payload.get("password")
    confirmation = payload.get("password_confirmation")

    if not display_name:
        return api_error("VALIDATION_ERROR", "Display name is required.", 400)
    if not email or not EMAIL_RE.match(email):
        return api_error("VALIDATION_ERROR", "A valid email address is required.", 400)
    if not isinstance(password, str) or not password.strip() or len(password) < 12:
        return api_error("VALIDATION_ERROR", "Password must be at least 12 characters.", 400)
    if password != confirmation:
        return api_error("PASSWORD_MISMATCH", "Password confirmation must match.", 400)
    return None


def normalize_email(value) -> str:
    return str(value or "").strip().lower()


def create_session(conn, user_id: str, config):
    token = new_session_token()
    expires_at = datetime.now(timezone.utc) + config.session_lifetime
    execute(
        conn,
        """
        INSERT INTO sessions (user_id, session_token_hash, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user_id, hash_session_token(token), expires_at),
    )
    return token


def set_session_cookie(response, token: str, config):
    response.set_cookie(
        config.session_cookie_name,
        token,
        httponly=True,
        secure=config.cookie_secure,
        samesite="Lax",
        max_age=int(config.session_lifetime.total_seconds()),
    )
