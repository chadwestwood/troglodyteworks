import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.seed_initial as seed_initial
from twe import config as config_module
from twe.app import create_app
from twe.authorization import can_request_capability
from twe.config import Config
from twe.responses import api_error
from twe.routes.auth import normalize_email, validate_registration_payload
from twe.security import hash_password, verify_password
from twe.services import local_asa


class FoundationTests(unittest.TestCase):
    def test_password_verification(self):
        password_hash = hash_password("correct horse battery staple")
        self.assertTrue(verify_password(password_hash, "correct horse battery staple"))
        self.assertFalse(verify_password(password_hash, "wrong password"))

    def test_session_required_route_returns_api_error(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        response = client.get("/api/v1/communities")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "UNAUTHENTICATED")

    def test_static_sign_in_page_is_served_for_local_review(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        response = client.get("/auth/sign-in.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sign In", response.data)

    def test_static_register_and_explore_pages_are_served(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        register = client.get("/auth/register.html")
        explore = client.get("/explore/")
        invite = client.get("/invite/example-token/")
        admin = client.get("/admin/")
        self.assertEqual(register.status_code, 200)
        self.assertIn(b"Create Account", register.data)
        self.assertEqual(explore.status_code, 200)
        self.assertIn(b"Explore", explore.data)
        self.assertEqual(invite.status_code, 200)
        self.assertIn(b"Community Invitation", invite.data)
        self.assertEqual(admin.status_code, 200)
        self.assertIn(b"Platform Admin", admin.data)
        community = client.get("/communities/cohorts-in-the-wild/")
        self.assertEqual(community.status_code, 200)
        self.assertIn(b"Connect a new game service", community.data)

    def test_genesis_page_includes_capability_aware_member_view(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        page = client.get(
            "/communities/cohorts-in-the-wild/game-servers/ark-survival-ascended/instances/genesis/"
        )
        script = client.get("/js/twe-pages.js")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Read-only community view", page.data)
        self.assertIn(b"Request Trog access", page.data)
        self.assertIn(b"data-capabilities-panel", page.data)
        self.assertIn(b"configureGenesisAccessView", script.data)
        self.assertIn(b"Your Community role cannot request this Capability.", script.data)

    def test_browser_cannot_self_assign_ownership_endpoint(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        client = app.test_client()
        response = client.post("/api/v1/communities/cohorts-in-the-wild/owner")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "NOT_FOUND")

    def test_role_restrictions(self):
        owner_access = {"role": "owner"}
        member_access = {"role": "member"}
        self.assertTrue(can_request_capability(owner_access, "instance.status"))
        self.assertTrue(can_request_capability(owner_access, "instance.restart"))
        self.assertFalse(can_request_capability(member_access, "instance.status"))
        self.assertFalse(can_request_capability(member_access, "instance.restart"))

    def test_unconfigured_health_does_not_pass(self):
        health = local_asa.health(Config(database_url="postgresql://unused"))
        self.assertEqual(health["overall_status"], "unknown")
        statuses = {check["status"] for check in health["checks"]}
        self.assertIn("not_configured", statuses)
        self.assertNotIn("passed", statuses)

    def test_configured_health_reports_ready_when_required_checks_pass(self):
        original_process_check = local_asa._process_check
        original_port_check = local_asa._port_check
        original_rcon_check = local_asa._rcon_check
        try:
            local_asa._process_check = lambda _expected: {
                "name": "process_running",
                "status": "passed",
                "message": "ok",
            }
            local_asa._port_check = lambda _host, _port: {
                "name": "port_reachable",
                "status": "passed",
                "message": "ok",
            }
            local_asa._rcon_check = lambda _config: {
                "name": "broadcasting",
                "status": "passed",
                "message": "ok",
            }
            health = local_asa.health(
                Config(
                    database_url="postgresql://unused",
                    asa_expected_process="ArkAscendedServer.exe",
                    asa_health_host="127.0.0.1",
                    asa_health_port=27020,
                    asa_rcon_host="127.0.0.1",
                    asa_rcon_port=27020,
                    asa_rcon_password="secret",
                )
            )
            self.assertEqual(health["overall_status"], "ready")
        finally:
            local_asa._process_check = original_process_check
            local_asa._port_check = original_port_check
            local_asa._rcon_check = original_rcon_check

    def test_configured_health_reports_offline_when_rcon_fails(self):
        original_process_check = local_asa._process_check
        original_port_check = local_asa._port_check
        original_rcon_check = local_asa._rcon_check
        try:
            local_asa._process_check = lambda _expected: {
                "name": "process_running",
                "status": "passed",
                "message": "ok",
            }
            local_asa._port_check = lambda _host, _port: {
                "name": "port_reachable",
                "status": "passed",
                "message": "ok",
            }
            local_asa._rcon_check = lambda _config: {
                "name": "broadcasting",
                "status": "failed",
                "message": "not ok",
            }
            health = local_asa.health(
                Config(
                    database_url="postgresql://unused",
                    asa_expected_process="ArkAscendedServer.exe",
                    asa_health_host="127.0.0.1",
                    asa_health_port=27020,
                    asa_rcon_host="127.0.0.1",
                    asa_rcon_port=27020,
                    asa_rcon_password="secret",
                )
            )
            self.assertEqual(health["overall_status"], "offline")
        finally:
            local_asa._process_check = original_process_check
            local_asa._port_check = original_port_check
            local_asa._rcon_check = original_rcon_check

    def test_restart_capability_is_disabled(self):
        restart = local_asa.capability_for("instance.restart")
        self.assertIsNotNone(restart)
        self.assertFalse(restart["available"])
        self.assertIn("not yet been approved", restart["unavailable_reason"])

    def test_installed_mods_uses_live_active_order_and_catalog_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config.json").write_text(
                json.dumps({"active_mod_ids": ["222", "111"]}),
                encoding="utf-8",
            )
            (root / "mod_catalog.json").write_text(
                json.dumps({"mods": [{"id": "111", "name": "Named Mod"}]}),
                encoding="utf-8",
            )
            mods = local_asa.installed_mods(
                Config(database_url="postgresql://unused", asa_panel_config_path=str(root / "config.json"))
            )

        self.assertEqual(
            mods,
            [
                {"id": "222", "name": "Mod 222"},
                {"id": "111", "name": "Named Mod"},
            ],
        )

    def test_error_structure(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        with app.app_context():
            response, status = api_error("FORBIDDEN", "Nope.", 403)
            self.assertEqual(status, 403)
            self.assertEqual(response.get_json(), {"error": {"code": "FORBIDDEN", "message": "Nope."}})

    def test_registration_validation(self):
        app = create_app(Config(database_url="postgresql://unused"), database=object())
        valid = {
            "display_name": "Alex",
            "email": "alex@example.com",
            "password": "eight888",
            "password_confirmation": "eight888",
        }
        with app.app_context():
            self.assertIsNone(validate_registration_payload(valid))

            mismatch = valid | {"password_confirmation": "different-password"}
            response, status = validate_registration_payload(mismatch)
            self.assertEqual(status, 400)
            self.assertEqual(response.get_json()["error"]["code"], "PASSWORD_MISMATCH")

            short = valid | {"password": "seven77", "password_confirmation": "seven77"}
            response, status = validate_registration_payload(short)
            self.assertEqual(status, 400)
            self.assertEqual(response.get_json()["error"]["code"], "VALIDATION_ERROR")

            privileged = valid | {"role": "owner"}
            response, status = validate_registration_payload(privileged)
            self.assertEqual(status, 400)
            self.assertEqual(response.get_json()["error"]["code"], "VALIDATION_ERROR")

    def test_email_normalization(self):
        self.assertEqual(normalize_email("  Alex@Example.COM "), "alex@example.com")

    def test_migration_contains_required_tables(self):
        migration = (ROOT / "migrations" / "0001_initial_twe.sql").read_text()
        grant_migration = (ROOT / "migrations" / "0002_capability_grants.sql").read_text()
        discord_migration = (ROOT / "migrations" / "0003_discord_foundation.sql").read_text()
        unlink_migration = (ROOT / "migrations" / "0004_discord_identity_unlink.sql").read_text()
        instance_access_migration = (ROOT / "migrations" / "0005_discord_instance_access_grants.sql").read_text()
        invitations_migration = (ROOT / "migrations" / "0006_community_invitations.sql").read_text()
        identities_migration = (ROOT / "migrations" / "0007_external_identities_oauth.sql").read_text()
        verified_installation_migration = (ROOT / "migrations" / "0008_discord_verified_installation.sql").read_text()
        mod_names_migration = (ROOT / "migrations" / "0009_discord_mod_names_capability.sql").read_text()
        provisioning_migration = (ROOT / "migrations" / "0010_hosting_instance_provisioning.sql").read_text()
        provider_migration = (ROOT / "migrations" / "0011_provider_foundation.sql").read_text()
        for table in [
            "users",
            "sessions",
            "communities",
            "community_memberships",
            "game_servers",
            "game_instances",
            "server_operations",
            "server_operation_checks",
            "audit_logs",
        ]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS server_operation_capability_grants", grant_migration)
        for table in ["discord_guild_installations", "discord_identities", "discord_channel_policies"]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", discord_migration)
        self.assertIn("discord_identities_linked_at_check", unlink_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS discord_instance_access_grants", instance_access_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS discord_instance_access_grant_capabilities", instance_access_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS discord_guild_authority_verifications", instance_access_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS community_invitations", invitations_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS community_invitation_redemptions", invitations_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS user_external_identities", identities_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS oauth_states", identities_migration)
        self.assertIn("UNIQUE (provider, provider_subject)", identities_migration)
        self.assertIn("code_verifier", verified_installation_migration)
        self.assertIn("requested_channel_ids", verified_installation_migration)
        self.assertIn("instance.mods.names.read", mod_names_migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS instance_provisioning_requests", provisioning_migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS provider_instance_id", provisioning_migration)
        for table in [
            "provider_connections",
            "provider_connection_secrets",
            "provider_oauth_states",
            "provider_resources",
        ]:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", provider_migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS provider_resource_id", provider_migration)
        self.assertIn("ADD COLUMN IF NOT EXISTS game_key", provider_migration)
        self.assertIn("enforce_game_server_provider_community", provider_migration)

    def test_seed_uses_environment_credentials(self):
        seed = (ROOT / "scripts" / "seed_initial.py").read_text()
        self.assertIn("TWE_INITIAL_USER_EMAIL", seed)
        self.assertIn("TWE_INITIAL_USER_PASSWORD", seed)
        self.assertNotIn("chadwestwood@gmail.com", seed)

    def test_env_value_quotes_are_cleaned(self):
        self.assertEqual(config_module._clean_env_value('"postgresql://example"'), "postgresql://example")
        self.assertEqual(config_module._clean_env_value("'secret'"), "secret")
        self.assertEqual(config_module._clean_env_value("plain"), "plain")

    def test_csv_values_are_normalized(self):
        self.assertEqual(config_module.parse_csv(" Chad@Example.com, admin@example.com "), ("chad@example.com", "admin@example.com"))
        self.assertEqual(config_module.parse_csv(""), ())

    def test_seed_loads_config_before_initial_credentials(self):
        seed = (ROOT / "scripts" / "seed_initial.py").read_text()
        self.assertLess(seed.index("config = load_config()"), seed.index('require_env("TWE_INITIAL_USER_EMAIL")'))

    def test_seed_existing_user_updates_password_hash(self):
        seed = (ROOT / "scripts" / "seed_initial.py").read_text()
        self.assertIn("password_hash = %s", seed)

    def test_operation_audit_capability_parameter_is_typed(self):
        route = (ROOT / "twe" / "routes" / "instances.py").read_text()
        self.assertIn("jsonb_build_object('capability', %s::text)", route)


if __name__ == "__main__":
    unittest.main()
