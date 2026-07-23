import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .hosting import ProviderInstanceState


class RailwayMinecraftError(RuntimeError):
    pass


class RailwayMinecraft:
    """Small, purpose-built Railway GraphQL client for the Minecraft beta."""

    def __init__(self, config):
        self.url = config.railway_api_url
        self.token = config.railway_api_token
        self.project_id = config.railway_project_id
        self.environment_id = config.railway_environment_id
        self.image = config.railway_minecraft_image
        self.curseforge_api_key = config.curseforge_api_key

    @property
    def configured(self):
        return all((self.token, self.project_id, self.environment_id, self.curseforge_api_key))

    def create_service(self, name):
        data = self._call("""
          mutation serviceCreate($input: ServiceCreateInput!) {
            serviceCreate(input: $input) { id }
          }
        """, {"input": {
            "projectId": self.project_id,
            "name": _service_name(name),
            "source": {"image": self.image},
        }})
        return data["serviceCreate"]["id"]

    def create_volume(self, service_id):
        data = self._call("""
          mutation volumeCreate($input: VolumeCreateInput!) {
            volumeCreate(input: $input) { id }
          }
        """, {"input": {
            "projectId": self.project_id,
            "environmentId": self.environment_id,
            "serviceId": service_id,
            "mountPath": "/data",
        }})
        return data["volumeCreate"]["id"]

    def set_variables(self, service_id, variables):
        self._call("""
          mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
            variableCollectionUpsert(input: $input)
          }
        """, {"input": {
            "projectId": self.project_id,
            "environmentId": self.environment_id,
            "serviceId": service_id,
            "variables": variables,
        }})

    def create_tcp_proxy(self, service_id):
        data = self._call("""
          mutation tcpProxyCreate($input: TCPProxyCreateInput!) {
            tcpProxyCreate(input: $input) {
              id domain proxyPort applicationPort
            }
          }
        """, {"input": {
            "environmentId": self.environment_id,
            "serviceId": service_id,
            "applicationPort": 25565,
        }})
        return data["tcpProxyCreate"]

    def deploy(self, service_id):
        data = self._call("""
          mutation serviceInstanceDeploy($serviceId: String!, $environmentId: String!) {
            serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId)
          }
        """, {"serviceId": service_id, "environmentId": self.environment_id})
        value = data.get("serviceInstanceDeploy")
        return value if isinstance(value, str) else None

    def status(self, service_id):
        data = self._call("""
          query deployments($input: DeploymentListInput!) {
            deployments(input: $input, first: 1) {
              edges { node { id status createdAt } }
            }
          }
        """, {"input": {
            "projectId": self.project_id,
            "environmentId": self.environment_id,
            "serviceId": service_id,
        }})
        edges = data["deployments"]["edges"]
        return edges[0]["node"] if edges else None

    def health(self, service_id):
        deployment = self.status(service_id)
        provider_status = (deployment or {}).get("status", "INITIALIZING")
        if provider_status == "SUCCESS":
            overall = "ready"
            check_status = "passed"
            message = "Railway reports the Minecraft service is running."
        elif provider_status in {"FAILED", "CRASHED", "REMOVED"}:
            overall = "offline"
            check_status = "failed"
            message = "Railway reports the Minecraft service is not running."
        else:
            overall = "degraded"
            check_status = "pending"
            message = "The Minecraft service is still starting or redeploying."
        return {
            "overall_status": overall,
            "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "checks": [{"name": "railway_deployment", "status": check_status, "message": message}],
        }

    def variables_for(self, plan):
        minecraft_memory = max(1024, int(plan["memory_mb"]) - 768)
        immutable = plan["immutable_plan"]
        if isinstance(immutable, str):
            immutable = json.loads(immutable)
        curseforge = immutable["curseforge"]
        return {
            "EULA": "TRUE",
            "TYPE": "AUTO_CURSEFORGE",
            "CF_API_KEY": self.curseforge_api_key,
            "CF_SLUG": str(curseforge["slug"]),
            "CF_FILE_ID": str(curseforge["file_id"]),
            "MEMORY": f"{minecraft_memory}M",
            "SERVER_NAME": str(plan["server_name"]),
            "MOTD": f"{plan['server_name']} · hosted by Troglodyte Works",
            "ENABLE_AUTOPAUSE": "FALSE",
            "USE_AIKAR_FLAGS": "TRUE",
        }

    def _call(self, query, variables):
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "TroglodyteWorks/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read(1_000_001))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RailwayMinecraftError("Railway could not be reached. The installation can be resumed safely.") from error
        if payload.get("errors"):
            # Railway error text can contain internal identifiers; log it server-side,
            # but expose a fixed message to the browser.
            raise RailwayMinecraftError("Railway rejected an installation step. The installation can be resumed safely.")
        if not isinstance(payload.get("data"), dict):
            raise RailwayMinecraftError("Railway returned an invalid response. The installation can be resumed safely.")
        return payload["data"]


def _service_name(value):
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    return f"twe-minecraft-{normalized[:40] or 'server'}"


class RailwayMinecraftHostingProvider:
    """Status bridge used by the generic Instance reconciliation layer."""

    def __init__(self, config):
        self.client = RailwayMinecraft(config)

    def create_instance(self, _spec):
        raise RailwayMinecraftError("Managed Minecraft must be created from an approved hosting plan.")

    def get_instance_status(self, provider_instance_id):
        deployment = self.client.status(provider_instance_id)
        status = (deployment or {}).get("status", "INITIALIZING")
        if status == "SUCCESS":
            normalized = "ready"
        elif status in {"FAILED", "CRASHED", "REMOVED"}:
            normalized = "failed"
        else:
            normalized = "installing"
        return ProviderInstanceState(provider_instance_id, normalized, status)

    def start_instance(self, provider_instance_id):
        self.client.deploy(provider_instance_id)
        return self.get_instance_status(provider_instance_id)

    def restart_instance(self, provider_instance_id):
        return self.start_instance(provider_instance_id)

    def stop_instance(self, _provider_instance_id):
        raise RailwayMinecraftError("Stopping managed Minecraft is not available in this beta.")
