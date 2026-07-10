import sys
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
        self.assertEqual(register.status_code, 200)
        self.assertIn(b"Create Account", register.data)
        self.assertEqual(explore.status_code, 200)
        self.assertIn(b"Explore", explore.data)

    def test_role_restrictions(self):
        self.assertTrue(can_request_capability("member", "instance.status"))
        self.assertFalse(can_request_capability("member", "instance.restart"))
        self.assertTrue(can_request_capability("owner", "instance.restart"))

    def test_unconfigured_health_does_not_pass(self):
        health = local_asa.health(Config(database_url="postgresql://unused"))
        self.assertEqual(health["overall_status"], "unknown")
        statuses = {check["status"] for check in health["checks"]}
        self.assertIn("not_configured", statuses)
        self.assertNotIn("passed", statuses)

    def test_restart_capability_is_disabled(self):
        restart = local_asa.capability_for("instance.restart")
        self.assertIsNotNone(restart)
        self.assertFalse(restart["available"])
        self.assertIn("not yet been approved", restart["unavailable_reason"])

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
            "password": "long-enough-password",
            "password_confirmation": "long-enough-password",
        }
        with app.app_context():
            self.assertIsNone(validate_registration_payload(valid))

            mismatch = valid | {"password_confirmation": "different-password"}
            response, status = validate_registration_payload(mismatch)
            self.assertEqual(status, 400)
            self.assertEqual(response.get_json()["error"]["code"], "PASSWORD_MISMATCH")

            short = valid | {"password": "short", "password_confirmation": "short"}
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

    def test_seed_uses_environment_credentials(self):
        seed = (ROOT / "scripts" / "seed_initial.py").read_text()
        self.assertIn("TWE_INITIAL_USER_EMAIL", seed)
        self.assertIn("TWE_INITIAL_USER_PASSWORD", seed)
        self.assertNotIn("chadwestwood@gmail.com", seed)

    def test_env_value_quotes_are_cleaned(self):
        self.assertEqual(config_module._clean_env_value('"postgresql://example"'), "postgresql://example")
        self.assertEqual(config_module._clean_env_value("'secret'"), "secret")
        self.assertEqual(config_module._clean_env_value("plain"), "plain")

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
