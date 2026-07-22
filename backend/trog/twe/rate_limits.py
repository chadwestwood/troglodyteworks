from __future__ import annotations

import hashlib
from dataclasses import dataclass

from flask import jsonify, request

from .db import execute, fetch_one


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    limit: int
    window_seconds: int


SENSITIVE_RULES = {
    ("POST", "/api/v1/auth/login"): RateLimitRule("auth.login.ip", 30, 15 * 60),
    ("POST", "/api/v1/auth/register"): RateLimitRule("auth.register.ip", 10, 60 * 60),
}


def rule_for_request(method: str, path: str) -> RateLimitRule | None:
    exact = SENSITIVE_RULES.get((method, path))
    if exact:
        return exact
    if method == "GET" and path.startswith("/api/v1/auth/") and path.endswith("/start"):
        return RateLimitRule("oauth.start.ip", 30, 10 * 60)
    if method in {"POST", "PATCH", "DELETE"} and "/invitations" in path:
        return RateLimitRule("community.invitations.ip", 120, 60 * 60)
    if method in {"POST", "PATCH", "DELETE"} and "/hosting-connections" in path:
        return RateLimitRule("hosting.connections.ip", 60, 60 * 60)
    if method in {"POST", "PATCH", "PUT", "DELETE"} and path.startswith("/api/v1/"):
        return RateLimitRule("api.mutation.ip", 180, 60)
    return None


def request_identifier() -> str:
    remote = request.remote_addr or "unknown"
    # Cloudflare overwrites this header on the canonical production hostname.
    # Ignore it on Railway preview URLs where a caller could supply it directly.
    host = request.host.split(":", 1)[0].lower()
    if host == "troglodyteworks.com":
        remote = request.headers.get("CF-Connecting-IP", remote).strip() or remote
    return hashlib.sha256(remote.encode("utf-8")).hexdigest()


def consume_request_limit(conn, rule: RateLimitRule, identifier_hash: str) -> tuple[bool, int]:
    row = fetch_one(
        conn,
        """
        INSERT INTO request_rate_limits
            (scope, identifier_hash, window_started_at, request_count, updated_at)
        VALUES (%s, %s, now(), 1, now())
        ON CONFLICT (scope, identifier_hash) DO UPDATE
        SET window_started_at = CASE
                WHEN request_rate_limits.window_started_at <= now() - (%s * interval '1 second')
                THEN now()
                ELSE request_rate_limits.window_started_at
            END,
            request_count = CASE
                WHEN request_rate_limits.window_started_at <= now() - (%s * interval '1 second')
                THEN 1
                ELSE request_rate_limits.request_count + 1
            END,
            updated_at = now()
        RETURNING request_count,
                  GREATEST(1, CEIL(EXTRACT(EPOCH FROM
                      (window_started_at + (%s * interval '1 second') - now())
                  )))::int AS retry_after
        """,
        (rule.scope, identifier_hash, rule.window_seconds, rule.window_seconds, rule.window_seconds),
    )
    execute(
        conn,
        "DELETE FROM request_rate_limits WHERE updated_at < now() - interval '2 days'",
    )
    count = int(row["request_count"])
    return count <= rule.limit, int(row["retry_after"])


def rate_limit_response(retry_after: int):
    response = jsonify({
        "error": {
            "code": "RATE_LIMITED",
            "message": "Too many requests. Try again later.",
        }
    })
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, retry_after))
    return response
