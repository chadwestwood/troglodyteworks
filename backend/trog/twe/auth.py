from datetime import datetime, timezone
from functools import wraps

from flask import current_app, g, request

from .db import execute, fetch_one
from .responses import api_error
from .security import hash_session_token


def current_user_from_cookie():
    token = request.cookies.get(current_app.config["TWE_CONFIG"].session_cookie_name)
    if not token:
        return None

    token_hash = hash_session_token(token)
    now = datetime.now(timezone.utc)
    with current_app.config["TWE_DB"].connect() as conn:
        user = fetch_one(
            conn,
            """
            SELECT users.id::text, users.email, users.display_name, users.profile_image_url
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.session_token_hash = %s
              AND sessions.revoked_at IS NULL
              AND sessions.expires_at > %s
            """,
            (token_hash, now),
        )
        if user:
            execute(
                conn,
                "UPDATE sessions SET last_activity_at = %s WHERE session_token_hash = %s",
                (now, token_hash),
            )
        return user


def require_user(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user_from_cookie()
        if not user:
            return api_error("UNAUTHENTICATED", "Authentication is required.", 401)
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def user_response(user):
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "display_name": user["display_name"],
        "profile_image_url": user.get("profile_image_url"),
    }
