import json
import re

from flask import Blueprint, current_app, g, jsonify, request

from ..auth import require_user
from ..authorization import membership_for_community
from ..db import execute, fetch_all, fetch_one
from ..responses import api_error
from ..services.curseforge_modpacks import CurseForgeModpacks, CurseForgeUnavailable
from ..services.railway_minecraft import RailwayMinecraft, RailwayMinecraftError


managed_hosting_bp = Blueprint("twe_managed_hosting", __name__)
MEMORY_OPTIONS = {4096: (45, 65), 6144: (65, 90), 8192: (85, 115)}


def _curseforge():
    config = current_app.config["TWE_CONFIG"]
    if not config.curseforge_api_key:
        return None
    return CurseForgeModpacks(config.curseforge_api_base_url, config.curseforge_api_key)


def _railway():
    return RailwayMinecraft(current_app.config["TWE_CONFIG"])


def _plan_payload(row):
    return {
        key: row.get(key) for key in (
            "id", "community_id", "server_name", "modpack_name", "modpack_version",
            "memory_mb", "estimated_monthly_min", "estimated_monthly_max", "status",
            "public_endpoint", "game_instance_id", "provider_deployment_id", "last_error",
            "created_at", "updated_at",
        )
    }


def _read_plan(conn, community_id, plan_id, user_id, lock=False):
    suffix = " FOR UPDATE" if lock else ""
    return fetch_one(conn, f"""
        SELECT p.id::text AS id, p.community_id::text AS community_id,
               p.requested_by::text AS requested_by, p.server_name,
               p.modpack_project_id, p.modpack_file_id, p.modpack_name,
               p.modpack_version, p.memory_mb, p.estimated_monthly_min,
               p.estimated_monthly_max, p.status, p.immutable_plan,
               p.provider_service_id, p.provider_volume_id,
               p.provider_tcp_proxy_id, p.provider_deployment_id,
               p.public_endpoint, p.game_instance_id::text AS game_instance_id,
               p.last_error, p.provisioning_started_at, p.completed_at,
               p.created_at, p.updated_at,
               c.slug AS community_slug
        FROM managed_minecraft_hosting_plans p
        JOIN communities c ON c.id=p.community_id
        WHERE p.id=%s AND p.community_id=%s AND p.requested_by=%s
        {suffix}
    """, (plan_id, community_id, user_id))


@managed_hosting_bp.get("/hosting/capabilities")
@require_user
def hosting_capabilities():
    config = current_app.config["TWE_CONFIG"]
    railway = _railway()
    return jsonify({
        "minecraft_java": True,
        "curseforge_search": bool(config.curseforge_api_key),
        "railway_installation": railway.configured,
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
            SELECT id::text, community_id::text, game_instance_id::text, server_name,
                   modpack_name, modpack_version, memory_mb, estimated_monthly_min,
                   estimated_monthly_max, status, public_endpoint,
                   provider_deployment_id, last_error, created_at, updated_at
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
    installation_available = _railway().configured
    status = "awaiting_installation" if installation_available else "awaiting_platform_configuration"
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
            WHERE requested_by=%s
              AND (status NOT IN ('cancelled','failed') OR provider_service_id IS NOT NULL)
            LIMIT 1
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
        "installation_available": installation_available,
        "next_step": (
            "Your choices are locked in. Review the final charge warning, then start installation."
            if installation_available else
            "The exact plan is saved. A TWE administrator must enable Railway hosting capacity before paid installation can begin."
        ),
    }), 201


@managed_hosting_bp.get("/communities/<community_id>/managed-hosting-plans/<plan_id>")
@require_user
def get_plan(community_id, plan_id):
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership or membership["role"] != "owner":
            return api_error("FORBIDDEN", "Only the Community Owner who approved this plan can view it.", 403)
        plan = _read_plan(conn, community_id, plan_id, g.current_user["id"])
        if not plan:
            return api_error("NOT_FOUND", "Hosting plan was not found.", 404)
        if plan["status"] == "provisioning" and plan["provider_service_id"]:
            try:
                deployment = _railway().status(plan["provider_service_id"])
                if deployment:
                    execute(conn, """
                        UPDATE managed_minecraft_hosting_plans
                        SET provider_deployment_id=%s, updated_at=now() WHERE id=%s
                    """, (deployment["id"], plan_id))
                    if deployment["status"] == "SUCCESS":
                        _finish_plan(conn, plan)
                    elif deployment["status"] in {"FAILED", "CRASHED", "REMOVED"}:
                        execute(conn, """
                            UPDATE managed_minecraft_hosting_plans
                            SET status='failed', last_error=%s, updated_at=now() WHERE id=%s
                        """, ("Minecraft did not start successfully. No duplicate server will be created if you retry.", plan_id))
            except RailwayMinecraftError:
                pass
            plan = _read_plan(conn, community_id, plan_id, g.current_user["id"])
        instance = None
        if plan["game_instance_id"]:
            instance = fetch_one(conn, "SELECT game_server_id::text FROM game_instances WHERE id=%s", (plan["game_instance_id"],))
    payload = _plan_payload(plan)
    if plan["game_instance_id"] and instance:
        payload["world_url"] = (
            f"/communities/{plan['community_slug']}/game-servers/minecraft-java/"
            f"instances/{_slug(plan['server_name'])}/?community_id={community_id}"
            f"&game_server_id={instance['game_server_id']}&instance_id={plan['game_instance_id']}"
        )
    return jsonify({"plan": payload})


@managed_hosting_bp.post("/communities/<community_id>/managed-hosting-plans/<plan_id>/install")
@require_user
def install_plan(community_id, plan_id):
    railway = _railway()
    if not railway.configured:
        return api_error("PROVIDER_NOT_CONFIGURED", "Railway Minecraft installation is not configured yet.", 503)
    with current_app.config["TWE_DB"].connect() as conn:
        membership = membership_for_community(conn, g.current_user["id"], community_id)
        if not membership or membership["role"] != "owner":
            return api_error("FORBIDDEN", "Only the Community Owner who approved this plan can install it.", 403)
        plan = _read_plan(conn, community_id, plan_id, g.current_user["id"], lock=True)
        if not plan:
            return api_error("NOT_FOUND", "Hosting plan was not found.", 404)
        if plan["status"] == "online":
            return jsonify({"plan": _plan_payload(plan)})
        if plan["status"] not in {"awaiting_installation", "awaiting_platform_configuration", "provisioning", "failed"}:
            return api_error("INVALID_STATE", "This hosting plan cannot be installed.", 409)
        execute(conn, """
            UPDATE managed_minecraft_hosting_plans
            SET status='provisioning', last_error=NULL,
                provisioning_started_at=COALESCE(provisioning_started_at,now()), updated_at=now()
            WHERE id=%s
        """, (plan_id,))

    try:
        # Each identifier is persisted immediately. Retrying resumes at the first
        # incomplete step instead of creating another paid Railway service.
        with current_app.config["TWE_DB"].connect() as conn:
            plan = _read_plan(conn, community_id, plan_id, g.current_user["id"], lock=True)
            if not plan["provider_service_id"]:
                service_id = railway.create_service(plan["server_name"])
                execute(conn, "UPDATE managed_minecraft_hosting_plans SET provider_service_id=%s,updated_at=now() WHERE id=%s", (service_id, plan_id))
            else:
                service_id = plan["provider_service_id"]
        with current_app.config["TWE_DB"].connect() as conn:
            plan = _read_plan(conn, community_id, plan_id, g.current_user["id"], lock=True)
            if not plan["provider_volume_id"]:
                volume_id = railway.create_volume(service_id)
                execute(conn, "UPDATE managed_minecraft_hosting_plans SET provider_volume_id=%s,updated_at=now() WHERE id=%s", (volume_id, plan_id))
            railway.set_variables(service_id, railway.variables_for(plan))
            if not plan["provider_tcp_proxy_id"]:
                proxy = railway.create_tcp_proxy(service_id)
                endpoint = f"{proxy['domain']}:{proxy['proxyPort']}"
                execute(conn, """
                    UPDATE managed_minecraft_hosting_plans
                    SET provider_tcp_proxy_id=%s,public_endpoint=%s,updated_at=now() WHERE id=%s
                """, (proxy["id"], endpoint, plan_id))
            deployment_id = railway.deploy(service_id)
            if deployment_id:
                execute(conn, "UPDATE managed_minecraft_hosting_plans SET provider_deployment_id=%s,updated_at=now() WHERE id=%s", (deployment_id, plan_id))
            plan = _read_plan(conn, community_id, plan_id, g.current_user["id"])
    except RailwayMinecraftError as error:
        with current_app.config["TWE_DB"].connect() as conn:
            execute(conn, """
                UPDATE managed_minecraft_hosting_plans
                SET status='failed',last_error=%s,updated_at=now() WHERE id=%s
            """, (str(error), plan_id))
        return api_error("PROVIDER_ERROR", str(error), 502)
    return jsonify({
        "plan": _plan_payload(plan),
        "next_step": "Minecraft is being installed. This page will update when the world is ready.",
    }), 202


def _finish_plan(conn, plan):
    game_server = fetch_one(conn, """
        INSERT INTO game_servers
            (community_id,name,slug,game_type,management_adapter,status,game_key)
        VALUES (%s,%s,'minecraft-java','Minecraft: Java Edition','railway','online','minecraft_java')
        ON CONFLICT (community_id,slug) DO UPDATE SET status='online',updated_at=now()
        RETURNING id::text
    """, (plan["community_id"], "Minecraft: Java Edition"))
    instance_slug = _slug(plan["server_name"])
    instance = fetch_one(conn, """
        INSERT INTO game_instances
            (game_server_id,name,slug,instance_type,game_identifier,status,
             hosting_provider,provider_instance_id,provider_state)
        VALUES (%s,%s,%s,'minecraft_world','minecraft_java','online','railway',%s,'online')
        ON CONFLICT (game_server_id,slug) DO UPDATE
        SET name=EXCLUDED.name,status='online',hosting_provider='railway',
            provider_instance_id=EXCLUDED.provider_instance_id,
            provider_state='online',updated_at=now()
        RETURNING id::text
    """, (game_server["id"], plan["server_name"], instance_slug, plan["provider_service_id"]))
    execute(conn, """
        UPDATE managed_minecraft_hosting_plans
        SET status='online',game_instance_id=%s,last_error=NULL,
            completed_at=now(),updated_at=now() WHERE id=%s
    """, (instance["id"], plan["id"]))


def _slug(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return normalized[:80] or "minecraft-world"
