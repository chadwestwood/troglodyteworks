import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


CAPABILITIES = [
    {
        "key": "instance.status",
        "name": "Check Status",
        "description": "Run deterministic health checks for this Instance.",
        "available": True,
        "requires_confirmation": False,
    },
    {
        "key": "instance.players.list",
        "name": "List Players",
        "description": "Player listing is planned for this Instance.",
        "available": False,
        "requires_confirmation": False,
        "unavailable_reason": "Player listing is not yet approved for this vertical slice.",
    },
    {
        "key": "instance.save",
        "name": "Save World",
        "description": "World save is planned for this Instance.",
        "available": False,
        "requires_confirmation": True,
        "unavailable_reason": "Live save execution has not yet been approved.",
    },
    {
        "key": "instance.restart",
        "name": "Restart Instance",
        "description": "Restart the Instance and verify that it returns to a ready state.",
        "available": False,
        "requires_confirmation": True,
        "unavailable_reason": "Live restart execution has not yet been approved.",
    },
]


def capabilities():
    return [cap.copy() for cap in CAPABILITIES]


def installed_mods(config):
    """Return active ASA mods in launch order without calling an external API."""
    if not config.asa_panel_config_path:
        raise RuntimeError("ASA panel configuration path is not configured.")
    panel_path = Path(config.asa_panel_config_path)
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    active_ids = [str(value).strip() for value in panel.get("active_mod_ids", []) if str(value).strip()]

    catalog_paths = [Path(__file__).resolve().parents[2] / "data" / "asa_mod_catalog.json"]
    catalog_paths.append(panel_path.parent / "mod_catalog.json")
    catalog_paths.extend(Path(value) for value in panel.get("mod_catalog_files", []))
    names = {}
    for catalog_path in catalog_paths:
        if not catalog_path.exists():
            continue
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = payload.get("mods", payload) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            mod_id = str(item.get("id") or item.get("modId") or "").strip()
            name = str(item.get("name") or item.get("title") or "").strip()
            if mod_id and name and (mod_id not in names or not name.startswith("Mod ")):
                names[mod_id] = name

    return [{"id": mod_id, "name": names.get(mod_id, f"Mod {mod_id}")} for mod_id in active_ids]


def capability_for(key: str):
    return next((cap for cap in capabilities() if cap["key"] == key), None)


def health(config):
    checks = [
        _process_check(config.asa_expected_process),
        _port_check(config.asa_health_host, config.asa_health_port),
        _rcon_check(config),
    ]
    statuses = {check["status"] for check in checks}
    if statuses == {"passed"}:
        overall = "ready"
    elif "failed" in statuses:
        overall = "offline"
    elif "passed" in statuses:
        overall = "degraded"
    else:
        overall = "unknown"
    return {
        "overall_status": overall,
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "checks": checks,
    }


def _process_check(expected_process: str | None):
    if not expected_process:
        return {
            "name": "process_running",
            "status": "not_configured",
            "message": "Expected process name is not configured.",
        }
    try:
        result = subprocess.run(
            ["pgrep", "-f", expected_process],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return {
            "name": "process_running",
            "status": "unknown",
            "message": "Process check could not be completed.",
        }
    if result.returncode == 0:
        return {
            "name": "process_running",
            "status": "passed",
            "message": "Expected ARK process was detected.",
        }
    return {
        "name": "process_running",
        "status": "failed",
        "message": "Expected ARK process was not detected.",
    }


def _port_check(host: str | None, port: int | None):
    if not host or not port:
        return {
            "name": "port_reachable",
            "status": "not_configured",
            "message": "Expected network host or port is not configured.",
        }
    try:
        with socket.create_connection((host, port), timeout=3):
            pass
    except OSError:
        return {
            "name": "port_reachable",
            "status": "failed",
            "message": "Expected network port did not respond.",
        }
    return {
        "name": "port_reachable",
        "status": "passed",
        "message": "Expected network port responded.",
    }


def _rcon_check(config):
    if not config.asa_rcon_host or not config.asa_rcon_port or not config.asa_rcon_password:
        return {
            "name": "broadcasting",
            "status": "not_configured",
            "message": "RCON status verification is not configured.",
        }
    try:
        from services.rcon import list_players

        list_players(
            host=config.asa_rcon_host,
            port=config.asa_rcon_port,
            password=config.asa_rcon_password,
        )
    except Exception:
        return {
            "name": "broadcasting",
            "status": "failed",
            "message": "The game server did not respond to the configured RCON status check.",
        }
    return {
        "name": "broadcasting",
        "status": "passed",
        "message": "The game server responded to the configured RCON status check.",
    }
