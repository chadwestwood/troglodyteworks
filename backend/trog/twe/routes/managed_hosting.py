import json

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import fetch_all, fetch_one
from ..responses import api_error
from ..services.curseforge_modpacks import CurseForgeModpacks, CurseForgeUnavailable


managed_hosting_bp = Blueprint("twe_managed_hosting", __name__)
MEMORY_OPTIONS = {4096: (45, 65), 6144: (65, 90), 8192: (85, 115)}


def _curseforge():
    config = current_app.config["TWE_CONFIG"]
    if not config.curseforge_api_key:
        return None
    return CurseForgeModpacks(config.curseforge_api_base_url, config.curseforge_api_key)


@managed_hosting_bp.get("/hosting/capabilities")
@require_user
def hosting_capabilities():
    config = current_app.config["TWE_CONFIG"]
    return jsonify({
        "minecraft_java": True,
        "curseforge_search": bool(config.curseforge_api_key),
        "railway_installation": False,
        "beta_limit": "One managed Minecraft server per Community Owner.",
        "memory_options": [
            {"memory_mb": memory, "estimated_monthly_min": cost[0], "estimated_monthly_max": cost[1]}
            for memory, cost in MEMORY_OPTIONS.items()
        ],
    })


@managed_hosting_bp.get("/hosting/curseforge/modpacks")
@require_user
def search_modpacks():
    query = str(request.args.get("query") or "").strip()
    if len(query) < 2 or len(query) > 80:
        return api_error("VALIDATION_ERROR", "Enter 2 to 80 characters to search CurseForge.", 400)
    client = _curseforge()
    if not client:
        return api_error("PROVIDER_NOT_CONFIGURED", "CurseForge search is not configured yet.", 503)
    try:
        return jsonify({"modpacks": client.search(query)})
    except CurseForgeUnavailable as error:
        return api_error("PROVIDER_UNAVAILABLE", str(error), 503)


@managed_hosting_bp.get("/hosting/curseforge/modpacks/<int:project_id>/files")
@require_user
def modpack_files(project_id):
    client = _curseforge()
    if not client:
        return api_error("PROVIDER_NOT_CONFIGURED", "CurseForge search is not configured yet.", 503)
    try:
        return jsonify({"files": client.files(project_id)})
    except CurseForgeUnavailable as error:
        return api_error("PROVIDER_UNAVAILABLE", str(error), 503)


@managed_hosting_bp.get("/communities/<community_id>/managed-hosting-plans")
@require_user
def list_plans(community_id):
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership or membership["role"] != "owner":
            return api_error("FORBIDDEN", "Only a Community Owner can view hosting plans.", 403)
        rows = fetch_all(conn, """
            SELECT id::text, server_name, modpack_name, modpack_version, memory_mb,
                   estimated_monthly_min, estimated_monthly_max, status, created_at
            FROM managed_minecraft_hosting_plans
            WHERE community_id=%s ORDER BY created_at DESC
        """, (community_id,))
    return jsonify({"plans": rows})


@managed_hosting_bp.post("/communities/<community_id>/managed-hosting-plans")
@require_user
def create_plan(community_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"server_name", "modpack_project_id", "modpack_file_id", "memory_mb", "accept_eula", "accept_estimated_cost", "accept_beta"}
    if set(payload) - allowed:
        return api_error("VALIDATION_ERROR", "The hosting request contains unsupported fields.", 400)
    try:
        project_id = int(payload.get("modpack_project_id"))
        file_id = int(payload.get("modpack_file_id"))
        memory_mb = int(payload.get("memory_mb"))
    except (TypeError, ValueError):
        return api_error("VALIDATION_ERROR", "Choose a CurseForge modpack, version, and memory size.", 400)
    server_name = str(payload.get("server_name") or "").strip()[:100]
    if not server_name or project_id < 1 or file_id < 1 or memory_mb not in MEMORY_OPTIONS:
        return api_error("VALIDATION_ERROR", "The Minecraft server choices are invalid.", 400)
    if not all(payload.get(key) is True for key in ("accept_eula", "accept_estimated_cost", "accept_beta")):
        return api_error("CONSENT_REQUIRED", "Accept the Minecraft EULA, cost estimate, and beta limits before continuing.", 400)
    client = _curseforge()
    if not client:
        return api_error("PROVIDER_NOT_CONFIGURED", "CurseForge validation is not configured yet.", 503)
    try:
        modpack, file_row = client.resolve(project_id, file_id)
    except CurseForgeUnavailable as error:
        return api_error("PROVIDER_UNAVAILABLE", str(error), 503)
    minimum, maximum = MEMORY_OPTIONS[memory_mb]
    status = "awaiting_platform_configuration"
    immutable = {
        "operation": "install_managed_minecraft_curseforge",
        "provider": "railway",
        "image": "itzg/minecraft-server",
        "server_name": server_name,
        "minecraft": {"edition": "java", "eula_accepted": True},
        "curseforge": {"project_id": project_id, "file_id": file_id, "slug": modpack["slug"]},
        "memory_mb": memory_mb,
        "estimated_monthly_usd": {"minimum": minimum, "maximum": maximum},
        "limits": {"beta_server_limit": 1, "public_protocol": "tcp"},
    }
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership or membership["role"] != "owner":
            return api_error("FORBIDDEN", "Only a Community Owner can request managed hosting.", 403)
        active = fetch_one(conn, """
            SELECT id FROM managed_minecraft_hosting_plans
            WHERE requested_by=%s AND status NOT IN ('cancelled','failed') LIMIT 1
        """, (g.current_user["id"],))
        if active:
            return api_error("BETA_LIMIT_REACHED", "The beta currently allows one managed Minecraft server per owner.", 409)
        plan = fetch_one(conn, """
            INSERT INTO managed_minecraft_hosting_plans
                (community_id,requested_by,server_name,modpack_project_id,modpack_file_id,
                 modpack_name,modpack_version,memory_mb,estimated_monthly_min,
                 estimated_monthly_max,status,immutable_plan)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING id::text,server_name,modpack_name,modpack_version,memory_mb,
                      estimated_monthly_min,estimated_monthly_max,status,created_at
        """, (community_id, g.current_user["id"], server_name, project_id, file_id,
                modpack["name"], file_row["display_name"], memory_mb, minimum, maximum,
                status, json.dumps(immutable)))
    return jsonify({
        "plan": plan,
        "installation_available": False,
        "next_step": "The exact plan is saved. A TWE administrator must enable Railway hosting capacity before paid installation can begin.",
    }), 201
