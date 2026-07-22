from __future__ import annotations

import hashlib
import json
import re
import secrets

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error


host_agents_bp = Blueprint("twe_host_agents", __name__)
SUPPORTED_GAMES = {"ark_survival_ascended", "minecraft_java"}
STATUS_VALUES = {"unknown", "offline", "starting", "degraded", "online", "failed"}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _owner(conn, community_id: str) -> bool:
    membership = membership_for_community(conn, g.current_user["id"], community_id)
    return bool(membership and membership["role"] == "owner")


@host_agents_bp.post("/communities/<community_id>/host-agents/pairings")
@require_user
def create_pairing(community_id):
    token = secrets.token_urlsafe(32)
    with current_app.config["TWE_DB"].connect() as conn:
        if not _owner(conn, community_id):
            return api_error("FORBIDDEN", "Only a Community Owner can pair a host computer.", 403)
        pairing = fetch_one(conn, """
            INSERT INTO host_agent_pairings (token_hash, community_id, created_by, expires_at)
            VALUES (%s, %s, %s, now() + interval '30 minutes')
            RETURNING id::text, expires_at
        """, (_hash(token), community_id, g.current_user["id"]))
    base = request.url_root.rstrip("/")
    return jsonify({"pairing": {
        "id": pairing["id"], "token": token, "expires_at": pairing["expires_at"],
        "command": f"python3 trog_host_agent.py pair --site {base} --token {token}",
    }}), 201


@host_agents_bp.get("/communities/<community_id>/host-agents")
@require_user
def list_agents(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not _owner(conn, community_id):
            return api_error("FORBIDDEN", "Only a Community Owner can view paired hosts.", 403)
        agents = fetch_all(conn, """
            SELECT ha.id::text, ha.name, ha.status, ha.platform, ha.version, ha.last_seen_at,
                   ha.provider_connection_id::text,
                   COALESCE(jsonb_agg(jsonb_build_object(
                     'id', pr.id::text, 'name', pr.display_name, 'game_key', pr.provider_game_key,
                     'status', pr.normalized_status, 'metadata', pr.metadata,
                     'bound_game_server_id', gs.id::text
                   ) ORDER BY pr.display_name) FILTER (WHERE pr.id IS NOT NULL), '[]'::jsonb) AS resources
            FROM host_agents ha
            LEFT JOIN provider_resources pr ON pr.provider_connection_id = ha.provider_connection_id AND pr.available
            LEFT JOIN game_servers gs ON gs.provider_resource_id = pr.id
            WHERE ha.community_id = %s
            GROUP BY ha.id ORDER BY ha.created_at DESC
        """, (community_id,))
    return jsonify({"agents": agents})


@host_agents_bp.post("/host-agents/pair")
def pair_agent():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token") or "")
    name = str(payload.get("name") or "Trog Host").strip()[:100]
    if not token or not name:
        return api_error("VALIDATION_ERROR", "A pairing token and host name are required.", 400)
    agent_secret = secrets.token_urlsafe(48)
    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            pairing = fetch_one(conn, """
                SELECT id::text, community_id::text, created_by::text
                FROM host_agent_pairings
                WHERE token_hash = %s AND consumed_at IS NULL AND expires_at > now()
                FOR UPDATE
            """, (_hash(token),))
            if not pairing:
                return api_error("PAIRING_UNAVAILABLE", "That pairing code is invalid or expired.", 404)
            connection = fetch_one(conn, """
                INSERT INTO provider_connections
                    (community_id, provider_key, display_name, auth_strategy, status,
                     external_account_id, granted_scopes, connected_by_user_id, connected_at, last_verified_at)
                VALUES (%s, 'self_hosted', %s, 'configuration', 'active', %s,
                        ARRAY['status:read','players:read','mods:read']::text[], %s, now(), now())
                RETURNING id::text
            """, (pairing["community_id"], name, secrets.token_hex(12), pairing["created_by"]))
            agent = fetch_one(conn, """
                INSERT INTO host_agents
                    (community_id, provider_connection_id, name, agent_key_hash, platform, version, last_seen_at)
                VALUES (%s,%s,%s,%s,%s,%s,now())
                RETURNING id::text
            """, (pairing["community_id"], connection["id"], name, _hash(agent_secret),
                    str(payload.get("platform") or "")[:100], str(payload.get("version") or "")[:40]))
            execute(conn, "UPDATE host_agent_pairings SET consumed_at = now() WHERE id = %s", (pairing["id"],))
    return jsonify({"agent": {"id": agent["id"], "secret": agent_secret}}), 201


def _agent_auth(conn, agent_id: str):
    header = request.headers.get("Authorization", "")
    secret = header[7:] if header.startswith("Bearer ") else ""
    if not secret or len(secret) > 512:
        return None
    return fetch_one(conn, """
        SELECT id::text, community_id::text, provider_connection_id::text
        FROM host_agents WHERE id = %s AND agent_key_hash = %s AND status <> 'revoked'
    """, (agent_id, _hash(secret)))


@host_agents_bp.post("/host-agents/<agent_id>/heartbeat")
def heartbeat(agent_id):
    payload = request.get_json(silent=True) or {}
    resources = payload.get("resources") or []
    if not isinstance(resources, list) or len(resources) > 20 or len(json.dumps(payload)) > 131072:
        return api_error("VALIDATION_ERROR", "The host report is too large.", 400)
    normalized = []
    for item in resources:
        if not isinstance(item, dict):
            return api_error("VALIDATION_ERROR", "A host resource is invalid.", 400)
        game_key = str(item.get("game_key") or "")
        external_id = str(item.get("external_id") or "").strip()[:200]
        if game_key not in SUPPORTED_GAMES or not external_id:
            return api_error("VALIDATION_ERROR", "The host reported an unsupported game.", 400)
        status = str(item.get("status") or "unknown")
        if status not in STATUS_VALUES:
            status = "unknown"
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        normalized.append((external_id, str(item.get("name") or game_key)[:150], game_key, status, metadata))
    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            agent = _agent_auth(conn, agent_id)
            if not agent:
                return api_error("UNAUTHORIZED", "The host agent credential is invalid.", 401)
            execute(conn, "UPDATE provider_resources SET available = false, updated_at = now() WHERE provider_connection_id = %s", (agent["provider_connection_id"],))
            for external_id, name, game_key, status, metadata in normalized:
                fetch_one(conn, """
                    INSERT INTO provider_resources
                        (provider_connection_id, resource_type, external_resource_id, display_name,
                         provider_game_key, normalized_status, provider_status, metadata,
                         available, discovered_at, last_seen_at, last_status_at)
                    VALUES (%s,'game_server_service',%s,%s,%s,%s,%s,%s::jsonb,true,now(),now(),now())
                    ON CONFLICT (provider_connection_id, resource_type, external_resource_id)
                    DO UPDATE SET display_name=EXCLUDED.display_name, provider_game_key=EXCLUDED.provider_game_key,
                      normalized_status=EXCLUDED.normalized_status, provider_status=EXCLUDED.provider_status,
                      metadata=EXCLUDED.metadata, available=true, last_seen_at=now(), last_status_at=now(), updated_at=now()
                    RETURNING id::text
                """, (agent["provider_connection_id"], external_id, name, game_key, status, status, json.dumps(metadata)))
            execute(conn, """
                UPDATE host_agents SET status='active', last_seen_at=now(), platform=%s, version=%s,
                    metadata=%s::jsonb, updated_at=now() WHERE id=%s
            """, (str(payload.get("platform") or "")[:100], str(payload.get("version") or "")[:40],
                    json.dumps(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}), agent_id))
            execute(conn, "UPDATE provider_connections SET last_verified_at=now(), status='active', updated_at=now() WHERE id=%s", (agent["provider_connection_id"],))
    return jsonify({"status": "accepted", "resource_count": len(normalized)})


@host_agents_bp.post("/communities/<community_id>/host-agents/resources/<resource_id>/connect")
@require_user
def connect_resource(community_id, resource_id):
    with current_app.config["TWE_DB"].connect() as conn:
        with conn.transaction():
            if not _owner(conn, community_id):
                return api_error("FORBIDDEN", "Only a Community Owner can connect a host.", 403)
            resource = fetch_one(conn, """
                SELECT pr.id::text, pr.display_name, pr.provider_game_key, pr.external_resource_id
                FROM provider_resources pr JOIN provider_connections pc ON pc.id=pr.provider_connection_id
                WHERE pr.id=%s AND pc.community_id=%s AND pc.provider_key='self_hosted' AND pr.available
                FOR UPDATE
            """, (resource_id, community_id))
            if not resource:
                return api_error("NOT_FOUND", "That discovered server is unavailable.", 404)
            existing = fetch_one(conn, "SELECT id::text FROM game_servers WHERE provider_resource_id=%s", (resource_id,))
            if existing:
                return jsonify({"game_server_id": existing["id"], "already_connected": True})
            slug = re.sub(r"[^a-z0-9]+", "-", resource["display_name"].lower()).strip("-")[:60] or "hosted-game"
            slug = f"{slug}-{resource_id[:8]}"
            server = fetch_one(conn, """
                INSERT INTO game_servers
                    (community_id,name,slug,game_type,management_adapter,status,provider_resource_id,game_key)
                VALUES (%s,%s,%s,%s,'self_hosted','unknown',%s,%s) RETURNING id::text
            """, (community_id, resource["display_name"], slug, resource["provider_game_key"], resource_id, resource["provider_game_key"]))
            fetch_one(conn, """
                INSERT INTO game_instances (game_server_id,name,slug,instance_type,game_identifier,status)
                VALUES (%s,%s,'primary','primary',%s,'unknown') RETURNING id::text
            """, (server["id"], resource["display_name"], resource["external_resource_id"]))
            execute(conn, "UPDATE provider_resources SET selected_at=now(), updated_at=now() WHERE id=%s", (resource_id,))
    return jsonify({"game_server_id": server["id"], "already_connected": False}), 201


@host_agents_bp.get("/communities/<community_id>/host-agent-installation-plans")
@require_user
def list_installation_plans(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not _owner(conn, community_id):
            return api_error("FORBIDDEN", "Only a Community Owner can view installation plans.", 403)
        plans = fetch_all(conn, """
            SELECT id::text, host_agent_id::text, game_key, server_name, modpack_provider,
                   modpack_project_id, modpack_file_id, memory_mb, status, immutable_plan,
                   approved_at, created_at
            FROM host_agent_installation_plans WHERE community_id=%s ORDER BY created_at DESC
        """, (community_id,))
    return jsonify({"plans": plans})


@host_agents_bp.post("/communities/<community_id>/host-agent-installation-plans")
@require_user
def preview_installation_plan(community_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"host_agent_id", "server_name", "modpack_project_id", "modpack_file_id", "memory_mb"}
    if set(payload) - allowed:
        return api_error("VALIDATION_ERROR", "The installation request contains unsupported fields.", 400)
    try:
        project_id = int(payload.get("modpack_project_id"))
        file_id = int(payload.get("modpack_file_id"))
        memory_mb = int(payload.get("memory_mb") or 4096)
    except (TypeError, ValueError):
        return api_error("VALIDATION_ERROR", "CurseForge project, file, and memory values are required.", 400)
    name = str(payload.get("server_name") or "").strip()[:100]
    if not name or project_id < 1 or file_id < 1 or not 2048 <= memory_mb <= 32768:
        return api_error("VALIDATION_ERROR", "The Minecraft installation values are invalid.", 400)
    with current_app.config["TWE_DB"].connect() as conn:
        if not _owner(conn, community_id):
            return api_error("FORBIDDEN", "Only a Community Owner can preview an installation.", 403)
        agent = fetch_one(conn, "SELECT id::text FROM host_agents WHERE id=%s AND community_id=%s AND status='active'", (payload.get("host_agent_id"), community_id))
        if not agent:
            return api_error("NOT_FOUND", "Choose an active paired host computer.", 404)
        immutable = {
            "operation": "install_minecraft_curseforge",
            "game_key": "minecraft_java", "server_name": name,
            "curseforge": {"project_id": project_id, "file_id": file_id},
            "memory_mb": memory_mb,
            "security": {"raw_shell": False, "requires_second_approval": True,
                         "install_root": "agent_managed", "rollback_required": True},
        }
        plan = fetch_one(conn, """
            INSERT INTO host_agent_installation_plans
                (community_id,host_agent_id,requested_by,game_key,server_name,modpack_provider,
                 modpack_project_id,modpack_file_id,memory_mb,status,immutable_plan)
            VALUES (%s,%s,%s,'minecraft_java',%s,'curseforge',%s,%s,%s,'awaiting_approval',%s::jsonb)
            RETURNING id::text,status,immutable_plan
        """, (community_id, agent["id"], g.current_user["id"], name, project_id, file_id,
                memory_mb, json.dumps(immutable)))
    return jsonify({"plan": plan, "execution_available": False,
                    "notice": "Review and approve this exact plan. Live installation remains disabled until CurseForge resolution and agent rollback verification are configured."}), 201


@host_agents_bp.post("/communities/<community_id>/host-agent-installation-plans/<plan_id>/approve")
@require_user
def approve_installation_plan(community_id, plan_id):
    with current_app.config["TWE_DB"].connect() as conn:
        if not _owner(conn, community_id):
            return api_error("FORBIDDEN", "Only a Community Owner can approve an installation.", 403)
        plan = fetch_one(conn, """
            UPDATE host_agent_installation_plans
            SET status='approved', approved_by=%s, approved_at=now(), updated_at=now()
            WHERE id=%s AND community_id=%s AND status='awaiting_approval'
            RETURNING id::text,status,immutable_plan,approved_at
        """, (g.current_user["id"], plan_id, community_id))
        if not plan:
            return api_error("INVALID_PLAN_STATE", "That plan is unavailable or already handled.", 409)
    return jsonify({"plan": plan, "execution_available": False,
                    "notice": "Approval is recorded. No remote command was executed."})
