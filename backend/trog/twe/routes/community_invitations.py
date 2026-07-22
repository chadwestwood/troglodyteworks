from datetime import datetime, timedelta, timezone
import json

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..security import hash_session_token, new_session_token

community_invitations_bp = Blueprint("twe_community_invitations", __name__)

ROLE_RANK = {"member": 1, "moderator": 2, "admin": 3, "owner": 4}
INVITATION_STATUSES = {"pending", "accepted", "declined", "revoked", "expired"}
MAX_INVITATION_USES = 100
MAX_INVITATION_DURATION_HOURS = 24 * 365


@community_invitations_bp.post("/communities/<community_id>/invitations")
@require_user
def create_invitation(community_id):
    payload = request.get_json(silent=True) or {}
    invitation_type = str(payload.get("invitation_type") or "").strip()
    initial_role = normalize_role(payload.get("initial_role") or "member")
    requires_approval = bool(payload.get("requires_approval", invitation_type == "link"))
    maximum_uses = parse_positive_int(payload.get("maximum_uses"), default=1)
    try:
        default_duration_hours = 24 if invitation_type == "link" else 168
        expires_at = parse_expiration(payload, default_hours=default_duration_hours)
    except (OverflowError, TypeError, ValueError):
        return api_error("VALIDATION_ERROR", "Invitation expiration is not valid.", 400)
    if invitation_type not in {"direct", "link"}:
        return api_error("VALIDATION_ERROR", "Invitation type must be direct or link.", 400)
    if not initial_role:
        return api_error("VALIDATION_ERROR", "Initial role is not allowed.", 400)
    if maximum_uses is None or maximum_uses > MAX_INVITATION_USES:
        return api_error("VALIDATION_ERROR", f"Maximum uses must be between 1 and {MAX_INVITATION_USES}.", 400)

    with current_app.config["TWE_DB"].connect() as conn:
        actor = require_invitation_manager(conn, community_id)
        if not actor:
            return api_error("FORBIDDEN", "You are not authorized to create invitations for this Community.", 403)
        if not can_grant_role(actor["role"], initial_role):
            return api_error("FORBIDDEN", "You cannot invite members into that role.", 403)
        community = fetch_one(conn, "SELECT id::text, name, slug FROM communities WHERE id = %s", (community_id,))
        if not community:
            return api_error("NOT_FOUND", "Community was not found.", 404)

        token = None
        token_hash = None
        invited_user_id = None
        if invitation_type == "direct":
            maximum_uses = 1
            invited_user = resolve_invited_user(conn, payload)
            if not invited_user:
                return api_error("USER_NOT_FOUND", "No existing TWE user matched that invitation target.", 404)
            invited_user_id = invited_user["id"]
            if membership_for_community(conn, invited_user_id, community_id):
                return api_error("ALREADY_MEMBER", "That user is already a member of this Community.", 409)
        else:
            token = new_session_token()
            token_hash = hash_session_token(token)

        try:
            invitation = fetch_one(
                conn,
                """
                INSERT INTO community_invitations
                    (community_id, invitation_type, invited_user_id, token_hash, initial_role,
                     requires_approval, maximum_uses, expires_at, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id::text, community_id::text, invitation_type, invited_user_id::text,
                          initial_role, requires_approval, maximum_uses, use_count, expires_at,
                          status, created_by_user_id::text, created_at, revoked_at
                """,
                (
                    community_id,
                    invitation_type,
                    invited_user_id,
                    token_hash,
                    initial_role,
                    requires_approval,
                    maximum_uses,
                    expires_at,
                    g.current_user["id"],
                ),
            )
        except Exception:
            return api_error("DUPLICATE_INVITATION", "An active invitation already exists for that user.", 409)

        audit(
            conn,
            g.current_user["id"],
            community_id,
            "community.invitation.create",
            "community_invitation",
            invitation["id"],
            {"invitation_type": invitation_type, "initial_role": initial_role, "requires_approval": requires_approval},
        )

    response = invitation_response(invitation, community)
    if token:
        response["token"] = token
        response["url"] = f"/invite/{token}/"
    return jsonify({"invitation": response}), 201


@community_invitations_bp.get("/communities/<community_id>/invitations")
@require_user
def list_invitations(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        actor = require_invitation_reader(conn, community_id)
        if not actor:
            return api_error("FORBIDDEN", "You are not authorized to view invitations for this Community.", 403)
        rows = fetch_all(
            conn,
            """
            SELECT ci.id::text, ci.community_id::text, ci.invitation_type, ci.invited_user_id::text,
                   ci.initial_role, ci.requires_approval, ci.maximum_uses, ci.use_count,
                   ci.expires_at, effective_invitation_status(ci.status, ci.expires_at) AS status,
                   ci.created_by_user_id::text, ci.revoked_by_user_id::text, ci.created_at,
                   ci.updated_at, ci.revoked_at, u.display_name AS invited_user_display_name,
                   u.email AS invited_user_email
            FROM community_invitations ci
            LEFT JOIN users u ON u.id = ci.invited_user_id
            WHERE ci.community_id = %s
            ORDER BY ci.created_at DESC
            """,
            (community_id,),
        )
    grantable_roles = [role for role in ("member", "moderator", "admin") if can_grant_role(actor["role"], role)]
    return jsonify({
        "current_user_role": actor["role"],
        "grantable_roles": grantable_roles,
        "invitations": [safe_invitation_row(row) for row in rows],
    })


@community_invitations_bp.post("/communities/<community_id>/invitations/<invitation_id>/revoke")
@require_user
def revoke_invitation(community_id, invitation_id):
    with current_app.config["TWE_DB"].connect() as conn:
        actor = require_invitation_manager(conn, community_id)
        if not actor:
            return api_error("FORBIDDEN", "You are not authorized to revoke invitations for this Community.", 403)
        invitation = fetch_one(
            conn,
            """
            UPDATE community_invitations
            SET status = 'revoked', revoked_by_user_id = %s, revoked_at = now(), updated_at = now()
            WHERE id = %s AND community_id = %s AND status = 'pending'
            RETURNING id::text, status, revoked_at
            """,
            (g.current_user["id"], invitation_id, community_id),
        )
        if not invitation:
            return api_error("NOT_FOUND", "Pending invitation was not found.", 404)
        audit(conn, g.current_user["id"], community_id, "community.invitation.revoke", "community_invitation", invitation_id, {})
    return jsonify({"invitation": invitation})


@community_invitations_bp.get("/community-invitations/pending")
@require_user
def list_my_pending_invitations():
    with current_app.config["TWE_DB"].connect() as conn:
        rows = fetch_all(
            conn,
            """
            SELECT ci.id::text, ci.community_id::text, ci.invitation_type,
                   ci.initial_role, ci.requires_approval, ci.expires_at,
                   effective_invitation_status(ci.status, ci.expires_at) AS status,
                   ci.created_at, c.name AS community_name, c.slug AS community_slug
            FROM community_invitations ci
            JOIN communities c ON c.id = ci.community_id
            WHERE ci.invited_user_id = %s
              AND ci.invitation_type = 'direct'
              AND effective_invitation_status(ci.status, ci.expires_at) = 'pending'
            ORDER BY ci.created_at DESC
            """,
            (g.current_user["id"],),
        )
    return jsonify({"invitations": [pending_direct_invitation_response(row) for row in rows]})


@community_invitations_bp.get("/communities/<community_id>/invitation-redemptions/pending")
@require_user
def list_pending_redemptions(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        actor = require_invitation_reader(conn, community_id)
        if not actor:
            return api_error("FORBIDDEN", "You are not authorized to view membership requests.", 403)
        rows = fetch_all(
            conn,
            """
            SELECT cir.id::text, cir.invitation_id::text, cir.user_id::text, cir.status,
                   cir.redeemed_at, u.display_name AS user_display_name, u.email AS user_email,
                   ci.initial_role, ci.invitation_type
            FROM community_invitation_redemptions cir
            JOIN community_invitations ci ON ci.id = cir.invitation_id
            JOIN users u ON u.id = cir.user_id
            WHERE ci.community_id = %s AND cir.status = 'pending_approval'
            ORDER BY cir.redeemed_at ASC
            """,
            (community_id,),
        )
    return jsonify({"redemptions": [pending_redemption_response(row) for row in rows]})


@community_invitations_bp.get("/community-invitations/<token>")
def read_link_invitation(token):
    token_hash = hash_session_token(token)
    with current_app.config["TWE_DB"].connect() as conn:
        invitation = invitation_by_token_hash(conn, token_hash)
        if not invitation:
            return api_error("INVITATION_NOT_FOUND", "Invitation was not found.", 404)
    return jsonify({"invitation": public_invitation_response(invitation)})


@community_invitations_bp.post("/community-invitations/<token>/accept")
@require_user
def accept_link_invitation(token):
    return redeem_invitation(token=token, invitation_id=None, decline=False)


@community_invitations_bp.post("/community-invitations/<token>/decline")
@require_user
def decline_link_invitation(token):
    return redeem_invitation(token=token, invitation_id=None, decline=True)


@community_invitations_bp.post("/community-invitations/direct/<invitation_id>/accept")
@require_user
def accept_direct_invitation(invitation_id):
    return redeem_invitation(token=None, invitation_id=invitation_id, decline=False)


@community_invitations_bp.post("/community-invitations/direct/<invitation_id>/decline")
@require_user
def decline_direct_invitation(invitation_id):
    return redeem_invitation(token=None, invitation_id=invitation_id, decline=True)


@community_invitations_bp.post("/communities/<community_id>/invitation-redemptions/<redemption_id>/approve")
@require_user
def approve_redemption(community_id, redemption_id):
    return decide_pending_redemption(community_id, redemption_id, approved=True)


@community_invitations_bp.post("/communities/<community_id>/invitation-redemptions/<redemption_id>/deny")
@require_user
def deny_redemption(community_id, redemption_id):
    return decide_pending_redemption(community_id, redemption_id, approved=False)


def redeem_invitation(token: str | None, invitation_id: str | None, decline: bool):
    token_hash = hash_session_token(token) if token else None
    with current_app.config["TWE_DB"].connect() as conn:
        invitation = invitation_by_token_hash(conn, token_hash) if token_hash else direct_invitation_for_user(conn, invitation_id, g.current_user["id"])
        if not invitation:
            return api_error("INVITATION_NOT_FOUND", "Invitation was not found.", 404)
        problem = validate_invitation_for_user(conn, invitation, g.current_user["id"])
        if problem:
            return problem
        if decline:
            redemption = record_decline(conn, invitation, g.current_user["id"])
            audit(conn, g.current_user["id"], invitation["community_id"], "community.invitation.decline", "community_invitation", invitation["id"], {})
            return jsonify({"redemption": redemption})

        increment = consume_invitation_use(conn, invitation)
        if not increment:
            return api_error("INVITATION_UNAVAILABLE", "Invitation can no longer be used.", 409)
        redemption_status = "pending_approval" if invitation["requires_approval"] else "accepted"
        redemption = create_redemption(conn, invitation, g.current_user["id"], redemption_status)
        if not invitation["requires_approval"]:
            create_membership(conn, invitation, g.current_user["id"])
            maybe_mark_invitation_accepted(conn, invitation)
        audit(
            conn,
            g.current_user["id"],
            invitation["community_id"],
            "community.invitation.accept",
            "community_invitation",
            invitation["id"],
            {"status": redemption_status},
        )
    return jsonify({"redemption": redemption})


def decide_pending_redemption(community_id: str, redemption_id: str, approved: bool):
    with current_app.config["TWE_DB"].connect() as conn:
        actor = require_invitation_manager(conn, community_id)
        if not actor:
            return api_error("FORBIDDEN", "You are not authorized to approve membership requests.", 403)
        row = fetch_one(
            conn,
            """
            SELECT cir.id::text, cir.user_id::text, ci.id::text AS invitation_id,
                   ci.community_id::text, ci.initial_role
            FROM community_invitation_redemptions cir
            JOIN community_invitations ci ON ci.id = cir.invitation_id
            WHERE cir.id = %s AND ci.community_id = %s AND cir.status = 'pending_approval'
            """,
            (redemption_id, community_id),
        )
        if not row:
            return api_error("NOT_FOUND", "Pending membership request was not found.", 404)
        if approved:
            if not can_grant_role(actor["role"], row["initial_role"]):
                return api_error("FORBIDDEN", "You cannot approve membership into that role.", 403)
            create_membership(conn, row, row["user_id"])
            redemption = fetch_one(
                conn,
                """
                UPDATE community_invitation_redemptions
                SET status = 'approved', approved_by_user_id = %s, approved_at = now()
                WHERE id = %s
                RETURNING id::text, status, approved_at
                """,
                (g.current_user["id"], redemption_id),
            )
            action = "community.invitation.approve"
        else:
            redemption = fetch_one(
                conn,
                """
                UPDATE community_invitation_redemptions
                SET status = 'denied', denied_by_user_id = %s, denied_at = now()
                WHERE id = %s
                RETURNING id::text, status, denied_at
                """,
                (g.current_user["id"], redemption_id),
            )
            action = "community.invitation.deny"
        audit(conn, g.current_user["id"], community_id, action, "community_invitation_redemption", redemption_id, {})
    return jsonify({"redemption": redemption})


def require_invitation_manager(conn, community_id: str):
    membership = membership_for_community(conn, g.current_user["id"], community_id)
    if membership and membership["role"] in {"owner", "admin", "moderator"}:
        return membership
    return None


def require_invitation_reader(conn, community_id: str):
    membership = membership_for_community(conn, g.current_user["id"], community_id)
    if membership and membership["role"] in {"owner", "admin", "moderator"}:
        return membership
    return None


def normalize_role(role) -> str | None:
    value = str(role or "").strip()
    aliases = {"community_member": "member", "member": "member", "moderator": "moderator", "admin": "admin"}
    return aliases.get(value)


def can_grant_role(actor_role: str, target_role: str) -> bool:
    return ROLE_RANK.get(actor_role, 0) > ROLE_RANK.get(target_role, 0)


def parse_positive_int(value, default: int):
    if value in {None, ""}:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_expiration(payload, default_hours=168):
    expires_at = payload.get("expires_at")
    if expires_at:
        text = str(expires_at).strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    duration_hours = parse_positive_int(payload.get("expires_in_hours"), default=default_hours)
    if duration_hours is None or duration_hours > MAX_INVITATION_DURATION_HOURS:
        raise ValueError("expiration duration is outside the allowed range")
    return datetime.now(timezone.utc) + timedelta(hours=duration_hours)


def resolve_invited_user(conn, payload):
    email = str(payload.get("email") or "").strip().lower()
    user_id = str(payload.get("user_id") or "").strip()
    if user_id:
        return fetch_one(conn, "SELECT id::text, email, display_name FROM users WHERE id = %s", (user_id,))
    if email:
        return fetch_one(conn, "SELECT id::text, email, display_name FROM users WHERE lower(email) = %s", (email,))
    return None


def invitation_by_token_hash(conn, token_hash: str):
    return fetch_one(
        conn,
        """
        SELECT ci.id::text, ci.community_id::text, ci.invitation_type, ci.invited_user_id::text,
               ci.initial_role, ci.requires_approval, ci.maximum_uses, ci.use_count,
               ci.expires_at, effective_invitation_status(ci.status, ci.expires_at) AS status,
               ci.created_by_user_id::text, ci.created_at, c.name AS community_name, c.slug AS community_slug
        FROM community_invitations ci
        JOIN communities c ON c.id = ci.community_id
        WHERE ci.token_hash = %s AND ci.invitation_type = 'link'
        """,
        (token_hash,),
    )


def direct_invitation_for_user(conn, invitation_id: str, user_id: str):
    return fetch_one(
        conn,
        """
        SELECT ci.id::text, ci.community_id::text, ci.invitation_type, ci.invited_user_id::text,
               ci.initial_role, ci.requires_approval, ci.maximum_uses, ci.use_count,
               ci.expires_at, effective_invitation_status(ci.status, ci.expires_at) AS status,
               ci.created_by_user_id::text, ci.created_at, c.name AS community_name, c.slug AS community_slug
        FROM community_invitations ci
        JOIN communities c ON c.id = ci.community_id
        WHERE ci.id = %s AND ci.invitation_type = 'direct' AND ci.invited_user_id = %s
        """,
        (invitation_id, user_id),
    )


def validate_invitation_for_user(conn, invitation, user_id: str):
    if invitation["status"] != "pending":
        return api_error("INVITATION_UNAVAILABLE", "Invitation is not active.", 409)
    if membership_for_community(conn, user_id, invitation["community_id"]):
        return api_error("ALREADY_MEMBER", "You are already a member of this Community.", 409)
    existing = fetch_one(
        conn,
        "SELECT id::text, status FROM community_invitation_redemptions WHERE invitation_id = %s AND user_id = %s",
        (invitation["id"], user_id),
    )
    if existing:
        return api_error("INVITATION_ALREADY_REDEEMED", "You have already responded to this invitation.", 409)
    return None


def consume_invitation_use(conn, invitation):
    return fetch_one(
        conn,
        """
        UPDATE community_invitations
        SET use_count = use_count + 1,
            status = CASE WHEN use_count + 1 >= maximum_uses THEN 'accepted' ELSE status END,
            updated_at = now()
        WHERE id = %s
          AND status = 'pending'
          AND (expires_at IS NULL OR expires_at > now())
          AND use_count < maximum_uses
        RETURNING id::text, use_count, maximum_uses, status
        """,
        (invitation["id"],),
    )


def create_redemption(conn, invitation, user_id: str, status: str):
    return fetch_one(
        conn,
        """
        INSERT INTO community_invitation_redemptions (invitation_id, user_id, status)
        VALUES (%s, %s, %s)
        RETURNING id::text, invitation_id::text, user_id::text, status, redeemed_at
        """,
        (invitation["id"], user_id, status),
    )


def record_decline(conn, invitation, user_id: str):
    redemption = create_redemption(conn, invitation, user_id, "declined")
    if invitation["invitation_type"] == "direct":
        execute(conn, "UPDATE community_invitations SET status = 'declined', updated_at = now() WHERE id = %s", (invitation["id"],))
    return redemption


def create_membership(conn, invitation, user_id: str):
    return fetch_one(
        conn,
        """
        INSERT INTO community_memberships (user_id, community_id, role)
        VALUES (%s, %s, %s)
        ON CONFLICT (user_id, community_id) DO NOTHING
        RETURNING id::text, role
        """,
        (user_id, invitation["community_id"], invitation["initial_role"]),
    )


def maybe_mark_invitation_accepted(conn, invitation):
    if invitation["invitation_type"] == "direct":
        execute(conn, "UPDATE community_invitations SET status = 'accepted', updated_at = now() WHERE id = %s", (invitation["id"],))


def safe_invitation_row(row):
    remaining = max(0, row["maximum_uses"] - row["use_count"])
    return {
        "id": row["id"],
        "community_id": row["community_id"],
        "invitation_type": row["invitation_type"],
        "invited_user": {
            "id": row["invited_user_id"],
            "display_name": row["invited_user_display_name"],
            "email": row["invited_user_email"],
        } if row["invited_user_id"] else None,
        "initial_role": row["initial_role"],
        "requires_approval": row["requires_approval"],
        "maximum_uses": row["maximum_uses"],
        "use_count": row["use_count"],
        "remaining_uses": remaining,
        "expires_at": row["expires_at"],
        "status": row["status"],
        "created_by_user_id": row["created_by_user_id"],
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
    }


def invitation_response(invitation, community):
    data = dict(invitation)
    data["community"] = community
    data["remaining_uses"] = data["maximum_uses"] - data["use_count"]
    return data


def public_invitation_response(invitation):
    return {
        "id": invitation["id"],
        "community": {"name": invitation["community_name"], "slug": invitation["community_slug"]},
        "initial_role": invitation["initial_role"],
        "requires_approval": invitation["requires_approval"],
        "maximum_uses": invitation["maximum_uses"],
        "use_count": invitation["use_count"],
        "remaining_uses": max(0, invitation["maximum_uses"] - invitation["use_count"]),
        "expires_at": invitation["expires_at"],
        "status": invitation["status"],
    }


def pending_direct_invitation_response(invitation):
    return {
        "id": invitation["id"],
        "community": {"id": invitation["community_id"], "name": invitation["community_name"], "slug": invitation["community_slug"]},
        "invitation_type": invitation["invitation_type"],
        "initial_role": invitation["initial_role"],
        "requires_approval": invitation["requires_approval"],
        "expires_at": invitation["expires_at"],
        "status": invitation["status"],
        "created_at": invitation["created_at"],
    }


def pending_redemption_response(redemption):
    return {
        "id": redemption["id"],
        "invitation_id": redemption["invitation_id"],
        "user": {
            "id": redemption["user_id"],
            "display_name": redemption["user_display_name"],
            "email": redemption["user_email"],
        },
        "initial_role": redemption["initial_role"],
        "invitation_type": redemption["invitation_type"],
        "status": redemption["status"],
        "redeemed_at": redemption["redeemed_at"],
    }


def audit(conn, user_id, community_id, action, target_type, target_id, details):
    execute(
        conn,
        """
        INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (user_id, community_id, action, target_type, target_id, json.dumps(details)),
    )
