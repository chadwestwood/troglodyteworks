import socket
import subprocess
from datetime import datetime, timezone


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


def capability_for(key: str):
    return next((cap for cap in capabilities() if cap["key"] == key), None)


def health(config):
    checks = [
        _process_check(config.asa_expected_process),
        _port_check(config.asa_health_host, config.asa_health_port),
        {
            "name": "broadcasting",
            "status": "not_configured",
            "message": "Game query or broadcasting confirmation is not configured yet.",
        },
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
