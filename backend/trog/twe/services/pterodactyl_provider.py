from __future__ import annotations

import json
from urllib import error, request

from .hosting import HostingProvider, InstanceSpec, ProviderInstanceState


class PterodactylHostingProvider(HostingProvider):
    def __init__(self, config):
        self._base_url = (config.pterodactyl_panel_url or "").rstrip("/")
        self._api_key = config.pterodactyl_api_key
        self._template = {
            "owner_user_id": config.pterodactyl_owner_user_id,
            "nest_id": config.pterodactyl_nest_id,
            "egg_id": config.pterodactyl_egg_id,
            "docker_image": config.pterodactyl_docker_image,
            "startup": config.pterodactyl_startup,
            "location_ids": [config.pterodactyl_location_id] if config.pterodactyl_location_id else [],
            "dedicated_ip": config.pterodactyl_dedicated_ip,
            "port_range": [],
            "memory": config.pterodactyl_memory_mb,
            "swap": config.pterodactyl_swap_mb,
            "disk": config.pterodactyl_disk_mb,
            "io": config.pterodactyl_io_weight,
            "cpu": config.pterodactyl_cpu_limit,
            "databases": config.pterodactyl_feature_databases,
            "backups": config.pterodactyl_feature_backups,
            "allocations": config.pterodactyl_feature_allocations,
            "environment": {
                "SERVER_MAP": config.pterodactyl_env_server_map,
                "MAX_PLAYERS": config.pterodactyl_env_max_players,
            },
        }
        self._validate_config()

    def create_instance(self, spec: InstanceSpec) -> ProviderInstanceState:
        payload = {
            "name": spec.name,
            "user": self._template["owner_user_id"],
            "external_id": spec.instance_id,
            "egg": self._template["egg_id"],
            "docker_image": self._template["docker_image"],
            "startup": self._template["startup"],
            "environment": self._resolved_environment(spec),
            "limits": {
                "memory": self._template["memory"],
                "swap": self._template["swap"],
                "disk": self._template["disk"],
                "io": self._template["io"],
                "cpu": self._template["cpu"],
            },
            "feature_limits": {
                "databases": self._template["databases"],
                "backups": self._template["backups"],
                "allocations": self._template["allocations"],
            },
            "allocation": {
                "default": None,
            },
            "deploy": {
                "locations": self._template["location_ids"],
                "dedicated_ip": self._template["dedicated_ip"],
                "port_range": self._template["port_range"],
            },
            "start_on_completion": True,
        }
        data = self._request_json("POST", "/api/application/servers", payload)
        attrs = data.get("attributes") or {}
        server_id = str(attrs.get("id") or "")
        status = str(attrs.get("status") or "installing")
        if not server_id:
            raise ValueError("Pterodactyl did not return a server id.")
        return ProviderInstanceState(provider_instance_id=server_id, provider_status=_normalize_status(status))

    def get_instance_status(self, provider_instance_id: str) -> ProviderInstanceState:
        data = self._request_json("GET", f"/api/application/servers/{provider_instance_id}")
        attrs = data.get("attributes") or {}
        raw_status = attrs.get("status")
        if raw_status is None and attrs.get("suspended"):
            raw_status = "failed"
        if raw_status is None:
            raw_status = "running"
        detail = attrs.get("description")
        return ProviderInstanceState(
            provider_instance_id=str(attrs.get("id") or provider_instance_id),
            provider_status=_normalize_status(str(raw_status)),
            detail=detail,
        )

    def start_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError("Pterodactyl runtime control is not part of this slice.")

    def stop_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError("Pterodactyl runtime control is not part of this slice.")

    def restart_instance(self, provider_instance_id: str) -> ProviderInstanceState:
        raise NotImplementedError("Pterodactyl runtime control is not part of this slice.")

    def _resolved_environment(self, spec: InstanceSpec):
        environment = dict(self._template["environment"])
        environment["SERVER_MAP"] = spec.map_key
        return environment

    def _validate_config(self):
        required = {
            "pterodactyl_panel_url": self._base_url,
            "pterodactyl_api_key": self._api_key,
            "pterodactyl_owner_user_id": self._template["owner_user_id"],
            "pterodactyl_egg_id": self._template["egg_id"],
            "pterodactyl_docker_image": self._template["docker_image"],
            "pterodactyl_startup": self._template["startup"],
            "pterodactyl_location_id": self._template["location_ids"][0] if self._template["location_ids"] else None,
            "pterodactyl_memory_mb": self._template["memory"],
            "pterodactyl_disk_mb": self._template["disk"],
            "pterodactyl_cpu_limit": self._template["cpu"],
            "pterodactyl_env_max_players": self._template["environment"].get("MAX_PLAYERS"),
        }
        missing = [name for name, value in required.items() if value in (None, "")]
        if missing:
            raise ValueError(f"Missing Pterodactyl configuration: {', '.join(missing)}")

    def _request_json(self, method: str, path: str, payload: dict | None = None):
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self._base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "Application/vnd.pterodactyl.v1+json",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                parsed = json.loads(response.read().decode("utf-8"))
                return parsed.get("attributes") and parsed or parsed.get("object") and parsed or parsed
        except error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Pterodactyl API request failed ({exc.code}). {payload[:400]}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Pterodactyl API request failed: {exc.reason}") from exc


def _normalize_status(raw_status: str) -> str:
    normalized = raw_status.lower().strip()
    if normalized in {"install_failed", "failed", "error", "suspended"}:
        return "failed"
    if normalized in {"running", "online", "ready"}:
        return "ready"
    if normalized in {"installing", "starting", "queued", "created"}:
        return "provisioning"
    return "provisioning"
