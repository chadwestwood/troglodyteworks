from datetime import datetime, timezone
import hashlib
import re

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import current_user_from_cookie, require_user, user_response
from ..db import execute, fetch_one
from ..responses import api_error
from ..security import hash_password, hash_session_token, new_session_token, verify_password

auth_bp = Blueprint("twe_auth", __name__)

REGISTRATION_FIELDS = {"display_name", "email", "password", "password_confirmation"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
LOGIN_RETRY_AFTER_SECONDS = 15 * 60
# A missing account still performs a real password-hash verification so callers
# cannot cheaply distinguish registered from unregistered email addresses.
DUMMY_PASSWORD_HASH = hash_password("twe-password-login-timing-placeholder")


@auth_bp.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password")
    if not email or not isinstance(password, str):
        return api_error("VALIDATION_ERROR", "Email and password are required.", 400)

    config = current_app.config["TWE_CONFIG"]
    with current_app.config["TWE_DB"].connect() as conn:
        identifier_hash = login_identifier_hash(email)
        # Serialize attempts for one normalized identifier across Railway replicas.
        # The hash itself contains no email address or other submitted credential.
        fetch_one(conn, "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (identifier_hash,))
        if login_failure_count(conn, identifier_hash) >= LOGIN_FAILURE_LIMIT:
            return login_rate_limit_response()
        user = fetch_one(
            conn,
            "SELECT id::text, email, display_name, password_hash FROM users WHERE lower(email) = %s",
            (email,),
        )
        password_hash = user["password_hash"] if user and user.get("password_hash") else DUMMY_PASSWORD_HASH
        password_valid = verify_password(password_hash, password)
        if not user or not user.get("password_hash") or not password_valid:
            record_login_failure(conn, identifier_hash)
            if login_failure_count(conn, identifier_hash) >= LOGIN_FAILURE_LIMIT:
                return login_rate_limit_response()
            return api_error("INVALID_CREDENTIALS", "Invalid email or password.", 401)

        clear_login_failures(conn, identifier_hash)
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


@auth_bp.patch("/account/profile")
@require_user
def update_profile():
    payload = request.get_json(silent=True) or {}
    display_name = str(payload.get("display_name") or "").strip()
    image_url = validate_image_value(payload.get("profile_image_url"))
    if not display_name or len(display_name) > 80:
        return api_error("VALIDATION_ERROR", "Display name must be between 1 and 80 characters.", 400)
    if image_url is False:
        return api_error("VALIDATION_ERROR", "Use a PNG, JPEG, or WebP image under 450 KB.", 400)
    with current_app.config["TWE_DB"].connect() as conn:
        user = fetch_one(conn, """
            UPDATE users SET display_name = %s, profile_image_url = %s, updated_at = now()
            WHERE id = %s
            RETURNING id::text, email, display_name, profile_image_url
        """, (display_name, image_url, g.current_user["id"]))
    return jsonify({"user": user_response(user)})


def validate_image_value(value):
    value = str(value or "").strip() or None
    if value is None:
        return None
    if len(value) > 600_000:
        return False
    if value.startswith("https://"):
        return value
    if re.match(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$", value):
        return value
    return False


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
    if not isinstance(password, str) or not password.strip() or len(password) < 8:
        return api_error("VALIDATION_ERROR", "Password must be at least 8 characters.", 400)
    if password != confirmation:
        return api_error("PASSWORD_MISMATCH", "Password confirmation must match.", 400)
    return None


def normalize_email(value) -> str:
    return str(value or "").strip().lower()


def login_identifier_hash(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def login_failure_count(conn, identifier_hash: str) -> int:
    row = fetch_one(
        conn,
        """
        SELECT count(*)::int AS count
        FROM password_login_failures
        WHERE identifier_hash = %s
          AND attempted_at >= now() - (%s * interval '1 second')
        """,
        (identifier_hash, LOGIN_FAILURE_WINDOW_SECONDS),
    )
    return int(row["count"] if row else 0)


def record_login_failure(conn, identifier_hash: str):
    # Keep the abuse ledger bounded without retaining long-term login metadata.
    execute(
        conn,
        "DELETE FROM password_login_failures WHERE attempted_at < now() - interval '1 day'",
    )
    execute(
        conn,
        "INSERT INTO password_login_failures (identifier_hash) VALUES (%s)",
        (identifier_hash,),
    )


def clear_login_failures(conn, identifier_hash: str):
    execute(
        conn,
        "DELETE FROM password_login_failures WHERE identifier_hash = %s",
        (identifier_hash,),
    )


def login_rate_limit_response():
    response = jsonify(
        {
            "error": {
                "code": "LOGIN_RATE_LIMITED",
                "message": "Too many sign-in attempts. Try again later.",
            }
        }
    )
    response.status_code = 429
    response.headers["Retry-After"] = str(LOGIN_RETRY_AFTER_SECONDS)
    return response


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
