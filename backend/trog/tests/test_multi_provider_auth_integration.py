import secrets
import sys
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.config import Config
from twe.db import Database, execute, fetch_all, fetch_one
from twe.oauth import ExternalProfile
from twe.routes import account_identities
from twe.routes.auth import create_session
from twe.security import hash_password
from tests.integration_database import load_integration_config


class MultiProviderAuthIntegrationTests(unittest.TestCase):
    def setUp(self):
        loaded = load_integration_config()
        self.config = Config(
            database_url=loaded.database_url,
            google_client_id="google-client",
            google_client_secret="google-secret",
            google_redirect_uri="http://localhost/api/v1/auth/google/callback",
            discord_client_id="discord-client",
            discord_client_secret="discord-secret",
            discord_redirect_uri="http://localhost/api/v1/auth/discord/callback",
        )
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        try:
            with self.db.connect() as conn:
                fetch_one(conn, "SELECT 1 FROM user_external_identities LIMIT 1")
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL or external identity migration unavailable: {exc.__class__.__name__}")
        self.app = create_app(self.config, database=self.db)
        self.client = self.app.test_client()
        self.original_exchange = account_identities.exchange_authorization_code
        account_identities.exchange_authorization_code = self.exchange
        self.profiles = {}
        self.created_users = []

    def tearDown(self):
        account_identities.exchange_authorization_code = self.original_exchange
        with self.db.connect() as conn:
            if self.created_users:
                execute(conn, "DELETE FROM users WHERE id = ANY(%s)", (self.created_users,))
            execute(conn, "DELETE FROM users WHERE email LIKE %s", (f"%-{self.suffix}@example.test",))

    def test_new_user_signs_up_with_google_and_existing_google_logs_into_same_user(self):
        self.profiles[("google", "google-code")] = ExternalProfile(
            provider="google",
            subject=f"google-sub-{self.suffix}",
            username="Mattertrala",
            email=f"matter-{self.suffix}@example.test",
            email_verified=True,
        )
        first = self._oauth_login("google", "google-code")
        self.assertEqual(first.status_code, 302)
        with self.db.connect() as conn:
            users = fetch_all(conn, "SELECT id::text FROM users WHERE email = %s", (f"matter-{self.suffix}@example.test",))
            identities = fetch_all(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'google' AND provider_subject = %s", (f"google-sub-{self.suffix}",))
        self.assertEqual(len(users), 1)
        self.assertEqual(len(identities), 1)

        second = self._oauth_login("google", "google-code")
        self.assertEqual(second.status_code, 302)
        with self.db.connect() as conn:
            users_after = fetch_all(conn, "SELECT id::text FROM users WHERE email = %s", (f"matter-{self.suffix}@example.test",))
        self.assertEqual(users_after, users)
        self.created_users.append(users[0]["id"])

    def test_new_user_signs_up_with_discord_and_discord_identity_is_synced(self):
        discord_subject = str(secrets.randbelow(8_000_000_000_000_000_000) + 1_000_000_000_000_000_000)
        discord_guild_id = str(int(discord_subject) + 1)
        self.profiles[("discord", "discord-code")] = ExternalProfile(
            provider="discord",
            subject=discord_subject,
            username="Mattertrala",
            email=f"discord-{self.suffix}@example.test",
            email_verified=True,
            managed_guilds=((discord_guild_id, "LizzLive", "manage_guild"),),
        )
        response = self._oauth_login("discord", "discord-code")
        self.assertEqual(response.status_code, 302)
        with self.db.connect() as conn:
            identity = fetch_one(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'discord' AND provider_subject = %s", (discord_subject,))
            discord = fetch_one(conn, "SELECT user_id::text FROM discord_identities WHERE discord_user_id = %s", (discord_subject,))
            managed = fetch_one(
                conn,
                "SELECT discord_guild_name, authority_source, can_manage_guild FROM discord_guild_authority_verifications WHERE user_id = %s AND discord_guild_id = %s",
                (identity["user_id"], discord_guild_id),
            )
        self.assertIsNotNone(identity)
        self.assertEqual(discord["user_id"], identity["user_id"])
        self.assertEqual(managed["discord_guild_name"], "LizzLive")
        self.assertEqual(managed["authority_source"], "manage_guild")
        self.assertTrue(managed["can_manage_guild"])
        identities = self.client.get("/api/v1/account/identities")
        self.assertEqual(identities.status_code, 200)
        self.assertEqual(identities.get_json()["identities"]["discord"]["provider_subject"], discord_subject)
        self.assertTrue(identities.get_json()["identities"]["discord"]["configured"])
        self.assertTrue(identities.get_json()["identities"]["google"]["configured"])
        guilds = self.client.get("/api/v1/discord/managed-guilds")
        self.assertEqual(guilds.status_code, 200)
        self.assertEqual(guilds.get_json()["guilds"][0]["id"], discord_guild_id)
        self.assertFalse(guilds.get_json()["refresh_required"])
        self.created_users.append(identity["user_id"])

    def test_local_user_connects_discord_and_conflict_is_rejected(self):
        discord_subject = str(secrets.randbelow(8_000_000_000_000_000_000) + 1_000_000_000_000_000_000)
        with self.db.connect() as conn:
            user = self._user(conn, "local")
            other = self._user(conn, "other")
            self._login(conn, self.client, user["id"])
            execute(
                conn,
                """
                INSERT INTO user_external_identities (user_id, provider, provider_subject)
                VALUES (%s, 'discord', %s)
                """,
                (other["id"], discord_subject),
            )
        self.profiles[("discord", "discord-conflict")] = ExternalProfile(provider="discord", subject=discord_subject)
        callback = self._oauth_link("discord", "discord-conflict")
        self.assertEqual(callback.status_code, 409)
        self.assertEqual(callback.get_json()["error"]["code"], "EXTERNAL_IDENTITY_CONFLICT")
        self.created_users.extend([user["id"], other["id"]])

    def test_google_email_match_does_not_silently_merge_local_user(self):
        with self.db.connect() as conn:
            local = self._user(conn, "same-email")
        self.profiles[("google", "google-email-match")] = ExternalProfile(
            provider="google",
            subject=f"different-google-{self.suffix}",
            username="Same Email Google",
            email=local["email"],
            email_verified=True,
        )
        response = self._oauth_login("google", "google-email-match")
        self.assertEqual(response.status_code, 302)
        with self.db.connect() as conn:
            identity = fetch_one(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'google' AND provider_subject = %s", (f"different-google-{self.suffix}",))
        self.assertIsNotNone(identity)
        self.assertNotEqual(identity["user_id"], local["id"])
        self.created_users.extend([local["id"], identity["user_id"]])

    def test_link_flow_never_creates_second_user_and_is_bound_to_session_user(self):
        with self.db.connect() as conn:
            user = self._user(conn, "link-owner")
            other = self._user(conn, "link-other")
            self._login(conn, self.client, user["id"])
        self.profiles[("google", "google-link")] = ExternalProfile(provider="google", subject=f"link-google-{self.suffix}")
        start = self.client.post("/api/v1/account/identities/google/connect", json={"return_to": "/discord/request-access/"})
        state = self._state_from_url(start.get_json()["oauth"]["authorization_url"])
        other_client = self.app.test_client()
        with self.db.connect() as conn:
            self._login(conn, other_client, other["id"])
        rejected = other_client.get(f"/api/v1/auth/google/callback?state={state}&code=google-link")
        self.assertEqual(rejected.status_code, 401)
        with self.db.connect() as conn:
            self.assertEqual(self._user_count(conn), 2)
        self.created_users.extend([user["id"], other["id"]])

    def test_oauth_state_is_one_time_and_invalid_state_is_rejected(self):
        self.profiles[("google", "one-time")] = ExternalProfile(provider="google", subject=f"one-time-{self.suffix}")
        start = self.client.get("/api/v1/auth/google/start")
        state = self._state_from_url(start.headers["Location"])
        first = self.client.get(f"/api/v1/auth/google/callback?state={state}&code=one-time")
        second = self.client.get(f"/api/v1/auth/google/callback?state={state}&code=one-time")
        invalid = self.client.get("/api/v1/auth/google/callback?state=nope&code=one-time")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(invalid.status_code, 400)
        with self.db.connect() as conn:
            identity = fetch_one(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'google' AND provider_subject = %s", (f"one-time-{self.suffix}",))
        self.created_users.append(identity["user_id"])

    def test_open_redirect_attempt_is_rejected_to_safe_default(self):
        self.profiles[("google", "redirect-code")] = ExternalProfile(provider="google", subject=f"redirect-{self.suffix}")
        start = self.client.get("/api/v1/auth/google/start?next=https://evil.example/")
        state = self._state_from_url(start.headers["Location"])
        callback = self.client.get(f"/api/v1/auth/google/callback?state={state}&code=redirect-code")
        self.assertEqual(callback.headers["Location"], "/communities/")
        with self.db.connect() as conn:
            identity = fetch_one(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'google' AND provider_subject = %s", (f"redirect-{self.suffix}",))
        self.created_users.append(identity["user_id"])

    def test_unlinking_final_authentication_method_is_prevented(self):
        self.profiles[("google", "final-code")] = ExternalProfile(provider="google", subject=f"final-{self.suffix}")
        response = self._oauth_login("google", "final-code")
        cookie = response.headers["Set-Cookie"].split(";", 1)[0].split("=", 1)[1]
        authed = self.app.test_client()
        authed.set_cookie(self.config.session_cookie_name, cookie)
        delete = authed.delete("/api/v1/account/identities/google")
        self.assertEqual(delete.status_code, 409)
        self.assertEqual(delete.get_json()["error"]["code"], "FINAL_AUTH_METHOD")
        with self.db.connect() as conn:
            identity = fetch_one(conn, "SELECT user_id::text FROM user_external_identities WHERE provider = 'google' AND provider_subject = %s", (f"final-{self.suffix}",))
        self.created_users.append(identity["user_id"])

    def exchange(self, provider, code, code_verifier, config, nonce=None):
        return self.profiles[(provider, code)]

    def _oauth_login(self, provider, code):
        start = self.client.get(f"/api/v1/auth/{provider}/start?next=/invite/example-token/")
        self.assertEqual(start.status_code, 302)
        state = self._state_from_url(start.headers["Location"])
        return self.client.get(f"/api/v1/auth/{provider}/callback?state={state}&code={code}")

    def _oauth_link(self, provider, code):
        start = self.client.post(f"/api/v1/account/identities/{provider}/connect", json={"return_to": "/discord/request-access/"})
        self.assertEqual(start.status_code, 200)
        state = self._state_from_url(start.get_json()["oauth"]["authorization_url"])
        return self.client.get(f"/api/v1/auth/{provider}/callback?state={state}&code={code}")

    def _state_from_url(self, url):
        return parse_qs(urlparse(url).query)["state"][0]

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text, email",
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), label),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)

    def _user_count(self, conn):
        return fetch_one(conn, "SELECT count(*) AS count FROM users WHERE email LIKE %s", (f"%-{self.suffix}@example.test",))["count"]


if __name__ == "__main__":
    unittest.main()
