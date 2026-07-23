import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.services.railway_minecraft import RailwayMinecraft, RailwayMinecraftError


class FakeResponse:
    def __init__(self, payload):
        self.body = BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount):
        return self.body.read(amount)


def config():
    return SimpleNamespace(
        railway_api_url="https://railway.example/graphql",
        railway_api_token="secret-token",
        railway_project_id="project-id",
        railway_environment_id="environment-id",
        railway_minecraft_image="itzg/minecraft-server:latest",
        curseforge_api_key="curseforge-secret",
    )


class RailwayMinecraftTests(unittest.TestCase):
    @patch("twe.services.railway_minecraft.urllib.request.urlopen")
    def test_creates_tcp_proxy_for_minecraft_port(self, opener):
        opener.return_value = FakeResponse({"data": {"tcpProxyCreate": {
            "id": "proxy-id", "domain": "roundhouse.proxy.rlwy.net",
            "proxyPort": 12345, "applicationPort": 25565,
        }}})
        result = RailwayMinecraft(config()).create_tcp_proxy("service-id")
        self.assertEqual(result["proxyPort"], 12345)
        request = opener.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["variables"]["input"]["applicationPort"], 25565)
        self.assertEqual(request.headers["Authorization"], "Bearer secret-token")

    def test_install_variables_pin_exact_curseforge_file(self):
        client = RailwayMinecraft(config())
        variables = client.variables_for({
            "server_name": "Cypres Pack",
            "memory_mb": 6144,
            "immutable_plan": {"curseforge": {"slug": "example-pack", "file_id": 789}},
        })
        self.assertEqual(variables["TYPE"], "AUTO_CURSEFORGE")
        self.assertEqual(variables["CF_SLUG"], "example-pack")
        self.assertEqual(variables["CF_FILE_ID"], "789")
        self.assertEqual(variables["MEMORY"], "5376M")

    @patch("twe.services.railway_minecraft.urllib.request.urlopen")
    def test_graphql_errors_are_redacted(self, opener):
        opener.return_value = FakeResponse({"errors": [{"message": "secret internal detail"}]})
        with self.assertRaisesRegex(RailwayMinecraftError, "rejected an installation step") as raised:
            RailwayMinecraft(config()).create_service("Test")
        self.assertNotIn("secret internal detail", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
