import secrets
import sys
import unittest
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.app import create_app
from twe.db import Database, execute, fetch_one
from twe.discord_api import DiscordAPIError, DiscordOAuthResult
from twe.discord_bot.authorization import authorize
from twe.routes import discord_access
from twe.routes.auth import create_session
from twe.security import hash_password
from tests.integration_database import load_integration_config


class DiscordInstanceAccessIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(
            load_integration_config(),
            discord_client_id="discord-client",
            discord_client_secret="discord-secret",
            discord_install_redirect_uri="https://example.test/api/v1/discord/oauth/callback",
            discord_bot_token="bot-token",
            discord_bot_permissions=274877975552,
        )
        self.db = Database(self.config.database_url)
        self.suffix = secrets.token_hex(8)
        self.guild_id = str(secrets.randbelow(8_000_000_000_000_000_000) + 1_000_000_000_000_000_000)
        self.discord_user_id = str(int(self.guild_id) + 1)
        try:
            with self.db.connect() as conn:
                self.owner = self._user(conn, "cohorts-owner")
                self.matter = self._user(conn, "mattertrala")
                self.member = self._user(conn, "ordinary-member")
                self.community = fetch_one(
                    conn,
                    "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                    (f"Cohorts {self.suffix}", f"cohorts-{self.suffix}", self.owner["id"]),
                )
                self.server = fetch_one(
                    conn,
                    """
                    INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter)
                    VALUES (%s, 'ARK Survival Ascended', 'ark-survival-ascended', 'ARK Survival Ascended', 'local_asa')
                    RETURNING id::text
                    """,
                    (self.community["id"],),
                )
                self.instance = fetch_one(
                    conn,
                    """
                    INSERT INTO game_instances (game_server_id, name, slug, instance_type, game_identifier, status)
                    VALUES (%s, 'Genesis', 'genesis', 'ark_map', 'Genesis_WP', 'online')
                    RETURNING id::text
                    """,
                    (self.server["id"],),
                )
                self._membership(conn, self.owner["id"], "owner")
                self._membership(conn, self.matter["id"], "member")
                self._membership(conn, self.member["id"], "member")
                self.app = create_app(self.config, database=self.db)
                self.owner_client = self.app.test_client()
                self.matter_client = self.app.test_client()
                self.member_client = self.app.test_client()
                self._login(conn, self.owner_client, self.owner["id"])
                self._login(conn, self.matter_client, self.matter["id"])
                self._login(conn, self.member_client, self.member["id"])
        except Exception as exc:
            raise unittest.SkipTest(f"PostgreSQL unavailable for instance access integration test: {exc.__class__.__name__}: {exc}")
        self.original_exchange = discord_access.exchange_guild_authorization
        self.original_installed = discord_access.installed_bot_guild
        self.oauth_user_id = self.discord_user_id
        self.oauth_permissions = 32
        discord_access.exchange_guild_authorization = self._exchange_discord
        discord_access.installed_bot_guild = lambda guild_id, _config: {"id": guild_id, "name": "LizzLive"}

    def tearDown(self):
        discord_access.exchange_guild_authorization = self.original_exchange
        discord_access.installed_bot_guild = self.original_installed
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (self.community["id"],))
            execute(conn, "DELETE FROM users WHERE id IN (%s,%s,%s)", (self.owner["id"], self.matter["id"], self.member["id"]))

    def test_mattertrala_request_to_active_lizzlive_grant(self):
        grant_id = self._create_request(channel_scope="allowlist")

        verification = self._verify_discord(grant_id, self.discord_user_id, permissions=32)
        self.assertEqual(verification["request"]["status"], "pending_provider_approval")

        denied = self.member_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={"approved_capabilities": ["instance.status.read"]},
        )
        self.assertEqual(denied.status_code, 403)

        install = self._install_trog(grant_id)
        self.assertIn("status=pending_provider_approval", install.headers["Location"])

        approval = self.owner_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={
                "approved_capabilities": [
                    "instance.status.read",
                    "instance.players.count.read",
                    "instance.players.names.read",
                ],
                "channel_scope": "allowlist",
            },
        )
        self.assertEqual(approval.status_code, 200)
        self.assertEqual(approval.get_json()["request"]["status"], "active")

        with self.db.connect() as conn:
            status = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
            count = authorize(conn, self.guild_id, "333", "public-user", "instance.players.count.read")
            names = authorize(conn, self.guild_id, "333", "public-user", "instance.players.names.read")
            wrong_channel = authorize(conn, self.guild_id, "444", "public-user", "instance.status.read")
            restart = authorize(conn, self.guild_id, "333", self.discord_user_id, "instance.restart.execute")
            lizzlive = fetch_one(conn, "SELECT id::text FROM communities WHERE slug = %s", (f"lizzlive-{self.suffix}",))

        self.assertTrue(status.allowed)
        self.assertIn("Cohorts", status.context.game_server_name)
        self.assertIn("Genesis", status.context.game_server_name)
        self.assertTrue(count.allowed)
        self.assertTrue(names.allowed)
        self.assertFalse(wrong_channel.allowed)
        self.assertEqual(wrong_channel.reason, "channel_unmapped")
        self.assertFalse(restart.allowed)
        self.assertIn(restart.reason, {"channel_unmapped", "capability_not_granted"})
        self.assertIsNone(lizzlive)

    def test_unlinked_discord_identity_cannot_complete_verification(self):
        grant_id = self._create_request()
        state = self._oauth_state(grant_id, "guild_verification")
        response = self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=verify-code")
        self.assertEqual(response.status_code, 302)
        self.assertIn("same+Discord+account", response.headers["Location"])

    def test_user_without_discord_guild_management_is_rejected(self):
        grant_id = self._create_request()
        self._link_identity(self.discord_user_id)
        self.oauth_permissions = 0
        state = self._oauth_state(grant_id, "guild_verification")
        response = self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=verify-code")
        self.assertEqual(response.status_code, 302)
        self.assertIn("did+not+confirm", response.headers["Location"])

    def test_revoked_grant_stops_access(self):
        grant_id = self._active_grant()
        revoke = self.owner_client.post(f"/api/v1/discord/instance-access-grants/{grant_id}/revoke")
        self.assertEqual(revoke.status_code, 200)
        with self.db.connect() as conn:
            decision = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "guild_not_connected")

    def test_owner_can_delegate_and_revoke_instance_operator_rights(self):
        grant_id = self._active_grant_for_channel("333")

        delegated = self.owner_client.patch(
            f"/api/v1/discord/instance-access-grants/{grant_id}/operator-rights",
            json={"enabled": True},
        )
        self.assertEqual(delegated.status_code, 200)
        with self.db.connect() as conn:
            restart = authorize(conn, self.guild_id, "333", self.discord_user_id, "instance.restart.execute")
            mods = authorize(conn, self.guild_id, "333", self.discord_user_id, "instance.mods.write")
        self.assertTrue(restart.allowed)
        self.assertTrue(mods.allowed)

        revoked = self.owner_client.patch(
            f"/api/v1/discord/instance-access-grants/{grant_id}/operator-rights",
            json={"enabled": False},
        )
        self.assertEqual(revoked.status_code, 200)
        with self.db.connect() as conn:
            restart = authorize(conn, self.guild_id, "333", self.discord_user_id, "instance.restart.execute")
        self.assertFalse(restart.allowed)
        self.assertEqual(restart.reason, "capability_not_granted")

    def test_channels_route_one_discord_server_to_different_instances(self):
        first_grant = self._active_grant_for_channel("333")
        with self.db.connect() as conn:
            family_community = fetch_one(
                conn,
                "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                (f"Family {self.suffix}", f"family-{self.suffix}", self.owner["id"]),
            )
            family_server = fetch_one(
                conn,
                "INSERT INTO game_servers (community_id,name,slug,game_type,management_adapter) VALUES (%s,'Family ARK','family-ark','ARK','local_asa') RETURNING id::text",
                (family_community["id"],),
            )
            family_instance = fetch_one(
                conn,
                "INSERT INTO game_instances (game_server_id,name,slug,instance_type,game_identifier,status) VALUES (%s,'Family Map','family-map','ark_map','Family','online') RETURNING id::text",
                (family_server["id"],),
            )
            installation = fetch_one(conn, "SELECT id::text FROM discord_guild_installations WHERE discord_guild_id = %s", (self.guild_id,))
            family_grant = fetch_one(
                conn,
                """
                INSERT INTO discord_instance_access_grants
                    (discord_guild_installation_id, provider_community_id, game_server_id, game_instance_id,
                     requested_by, requester_discord_user_id, consumer_discord_guild_id, status, channel_scope,
                     requested_channel_ids, provider_approved_by, provider_approved_at, discord_approved_by,
                     discord_approver_user_id, discord_approved_at, installed_at, activated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'active','allowlist',ARRAY['444'],%s,now(),%s,%s,now(),now(),now())
                RETURNING id::text
                """,
                (installation["id"], family_community["id"], family_server["id"], family_instance["id"],
                 self.matter["id"], self.discord_user_id, self.guild_id, self.owner["id"],
                 self.matter["id"], self.discord_user_id),
            )
            execute(conn, "INSERT INTO discord_instance_access_grant_capabilities (discord_instance_access_grant_id,capability,granted_by) VALUES (%s,'instance.status.read',%s)", (family_grant["id"], self.owner["id"]))

            genesis = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
            family = authorize(conn, self.guild_id, "444", "public-user", "instance.status.read")
            unmapped = authorize(conn, self.guild_id, "555", "public-user", "instance.status.read")

            execute(conn, "DELETE FROM communities WHERE id = %s", (family_community["id"],))

        self.assertTrue(genesis.allowed)
        self.assertEqual(genesis.context.instance_access_grant_id, first_grant)
        self.assertTrue(family.allowed)
        self.assertEqual(family.context.instance_name, "Family Map")
        self.assertFalse(unmapped.allowed)
        self.assertEqual(unmapped.reason, "channel_unmapped")

    def test_same_instance_can_route_to_channels_in_two_discord_servers(self):
        first_grant = self._active_grant_for_channel("333")
        second_guild = str(int(self.guild_id) + 500)
        with self.db.connect() as conn:
            installation = fetch_one(conn, """
                INSERT INTO discord_guild_installations
                    (discord_guild_id, community_id, game_server_id, installed_by)
                VALUES (%s,%s,%s,%s) RETURNING id::text
            """, (second_guild, self.community["id"], self.server["id"], self.matter["id"]))
            second = fetch_one(conn, """
                INSERT INTO discord_instance_access_grants
                    (discord_guild_installation_id, provider_community_id, game_server_id, game_instance_id,
                     requested_by, requester_discord_user_id, consumer_discord_guild_id, status,
                     channel_scope, requested_channel_ids, provider_approved_by, provider_approved_at,
                     discord_approved_by, discord_approver_user_id, discord_approved_at, installed_at, activated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'active','allowlist',ARRAY['777'],%s,now(),%s,%s,now(),now(),now())
                RETURNING id::text
            """, (installation["id"], self.community["id"], self.server["id"], self.instance["id"],
                    self.matter["id"], self.discord_user_id, second_guild, self.owner["id"],
                    self.matter["id"], self.discord_user_id))
            execute(conn, """
                INSERT INTO discord_instance_access_grant_capabilities
                    (discord_instance_access_grant_id, capability, granted_by)
                VALUES (%s,'instance.status.read',%s)
            """, (second["id"], self.owner["id"]))
            lizzlive = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
            mattertrala = authorize(conn, second_guild, "777", "public-user", "instance.status.read")
            wrong_channel = authorize(conn, second_guild, "333", "public-user", "instance.status.read")

        self.assertTrue(lizzlive.allowed)
        self.assertEqual(lizzlive.context.instance_access_grant_id, first_grant)
        self.assertTrue(mattertrala.allowed)
        self.assertEqual(mattertrala.context.instance_access_grant_id, second["id"])
        self.assertEqual(mattertrala.context.instance_name, "Genesis")
        self.assertFalse(wrong_channel.allowed)
        self.assertEqual(wrong_channel.reason, "channel_unmapped")

    def test_failed_instance_is_treated_as_a_stale_target(self):
        self._active_grant()
        with self.db.connect() as conn:
            execute(conn, "UPDATE game_instances SET status = 'failed' WHERE id = %s", (self.instance["id"],))
            decision = authorize(conn, self.guild_id, "333", "public-user", "instance.status.read")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "guild_not_connected")

    def test_discord_oauth_state_cannot_be_replayed(self):
        grant_id = self._create_request()
        self._link_identity(self.discord_user_id)
        state = self._oauth_state(grant_id, "guild_verification")

        first = self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=first-code")
        replay = self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=replay-code")

        self.assertEqual(first.status_code, 302)
        self.assertEqual(replay.status_code, 400)
        self.assertEqual(replay.get_json()["error"]["code"], "INVALID_OAUTH_STATE")

    def test_provider_can_deny_pending_request(self):
        grant_id = self._create_request()
        denied = self.owner_client.post(f"/api/v1/discord/instance-access-requests/{grant_id}/provider-denial")
        self.assertEqual(denied.status_code, 200)
        self.assertEqual(denied.get_json()["request"]["status"], "denied")
        oauth = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/oauth-state",
            json={"purpose": "guild_verification", "discord_guild_id": self.guild_id},
        )
        self.assertEqual(oauth.status_code, 409)

    def test_installation_is_not_recorded_when_bot_cannot_confirm_guild(self):
        grant_id = self._create_request()
        self._verify_discord(grant_id, self.discord_user_id, permissions=32)

        def missing_bot(_guild_id, _config):
            raise DiscordAPIError("not installed")

        discord_access.installed_bot_guild = missing_bot
        callback = self._install_trog(grant_id)
        self.assertEqual(callback.status_code, 302)
        self.assertIn("could+not+confirm", callback.headers["Location"])
        request_data = self.matter_client.get(f"/api/v1/discord/instance-access-requests/{grant_id}").get_json()["request"]
        self.assertIsNone(request_data["discord_guild_installation_id"])

    def test_browser_cannot_submit_unverified_discord_claims(self):
        grant_id = self._create_request()
        identity = self.matter_client.post("/api/v1/discord/identity/link", json={"discord_user_id": self.discord_user_id})
        verification = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/discord-verification",
            json={"discord_guild_id": self.guild_id, "permissions": 32},
        )
        installation = self.matter_client.post(f"/api/v1/discord/instance-access-requests/{grant_id}/bot-installation")
        self.assertEqual(identity.status_code, 404)
        self.assertEqual(verification.status_code, 404)
        self.assertEqual(installation.status_code, 404)

    def test_cross_community_instance_is_rejected(self):
        with self.db.connect() as conn:
            other_owner = self._user(conn, "other-owner")
            other_community = fetch_one(
                conn,
                "INSERT INTO communities (name, slug, created_by) VALUES (%s,%s,%s) RETURNING id::text",
                (f"Other {self.suffix}", f"other-{self.suffix}", other_owner["id"]),
            )
            other_server = fetch_one(
                conn,
                "INSERT INTO game_servers (community_id, name, slug, game_type, management_adapter) VALUES (%s,'Other','other','ARK','local_asa') RETURNING id::text",
                (other_community["id"],),
            )
            other_instance = fetch_one(
                conn,
                "INSERT INTO game_instances (game_server_id, name, slug, instance_type, game_identifier) VALUES (%s,'Other Map','other-map','ark_map','Other') RETURNING id::text",
                (other_server["id"],),
            )
        response = self.matter_client.post(
            "/api/v1/discord/instance-access-requests",
            json={
                "provider_community_id": self.community["id"],
                "game_instance_id": other_instance["id"],
                "requested_capabilities": ["instance.status.read"],
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"]["code"], "INSTANCE_NOT_FOUND")
        with self.db.connect() as conn:
            execute(conn, "DELETE FROM communities WHERE id = %s", (other_community["id"],))
            execute(conn, "DELETE FROM users WHERE id = %s", (other_owner["id"],))

    def test_static_request_access_page_is_served(self):
        response = self.matter_client.get("/discord/request-access/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trog Discord Access", response.data)
        self.assertIn(b"data-discord-guild-select", response.data)
        self.assertIn(b"Refresh Discord", response.data)
        self.assertIn(b"servers</button>", response.data)
        self.assertNotIn(b"paste the Discord server ID", response.data)

    def _active_grant(self):
        grant_id = self._create_request()
        self._verify_discord(grant_id, self.discord_user_id, permissions=32)
        install = self._install_trog(grant_id)
        self.assertEqual(install.status_code, 302)
        approval = self.owner_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={"approved_capabilities": ["instance.status.read"]},
        )
        self.assertEqual(approval.status_code, 200)
        return grant_id

    def _active_grant_for_channel(self, channel_id):
        response = self.matter_client.post(
            "/api/v1/discord/instance-access-requests",
            json={
                "provider_community_id": self.community["id"],
                "game_instance_id": self.instance["id"],
                "requested_capabilities": ["instance.status.read"],
                "channel_scope": "allowlist",
                "allowed_channel_ids": [channel_id],
            },
        )
        self.assertEqual(response.status_code, 201)
        grant_id = response.get_json()["request"]["id"]
        self._verify_discord(grant_id, self.discord_user_id, permissions=32)
        self._install_trog(grant_id)
        approval = self.owner_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/provider-approval",
            json={"approved_capabilities": ["instance.status.read"], "channel_scope": "allowlist"},
        )
        self.assertEqual(approval.status_code, 200)
        return grant_id

    def _create_request(self, channel_scope="all"):
        response = self.matter_client.post(
            "/api/v1/discord/instance-access-requests",
            json={
                "provider_community_id": self.community["id"],
                "game_instance_id": self.instance["id"],
                "requested_capabilities": [
                    "instance.status.read",
                    "instance.players.count.read",
                    "instance.players.names.read",
                ],
                "channel_scope": channel_scope,
                "allowed_channel_ids": ["333"] if channel_scope == "allowlist" else [],
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["request"]["id"]

    def _verify_discord(self, grant_id, discord_user_id, permissions):
        self._link_identity(discord_user_id)
        self.oauth_user_id = discord_user_id
        self.oauth_permissions = permissions
        state = self._oauth_state(grant_id, "guild_verification")
        response = self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=verify-code")
        self.assertEqual(response.status_code, 302)
        request_data = self.matter_client.get(f"/api/v1/discord/instance-access-requests/{grant_id}")
        self.assertEqual(request_data.status_code, 200)
        return request_data.get_json()

    def _link_identity(self, discord_user_id):
        with self.db.connect() as conn:
            execute(
                conn,
                "INSERT INTO discord_identities (discord_user_id,user_id,linked_at) VALUES (%s,%s,now()) ON CONFLICT (discord_user_id) DO UPDATE SET user_id=EXCLUDED.user_id, linked_at=now()",
                (discord_user_id, self.matter["id"]),
            )

    def _oauth_state(self, grant_id, purpose):
        payload = {"purpose": purpose}
        if purpose == "guild_verification":
            payload["discord_guild_id"] = self.guild_id
        response = self.matter_client.post(
            f"/api/v1/discord/instance-access-requests/{grant_id}/oauth-state",
            json=payload,
        )
        self.assertEqual(response.status_code, 200)
        url = response.get_json()["oauth"]["authorization_url"]
        params = parse_qs(urlparse(url).query)
        self.assertEqual(params["redirect_uri"], [self.config.discord_install_redirect_uri])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        if purpose == "bot_install":
            self.assertEqual(params["guild_id"], [self.guild_id])
            self.assertEqual(params["disable_guild_select"], ["true"])
        return params["state"][0]

    def _install_trog(self, grant_id):
        state = self._oauth_state(grant_id, "bot_install")
        return self.matter_client.get(f"/api/v1/discord/oauth/callback?state={state}&code=install-code")

    def _exchange_discord(self, _code, _code_verifier, _config):
        return DiscordOAuthResult(
            user_id=self.oauth_user_id,
            guilds=({"id": self.guild_id, "name": "LizzLive", "permissions": str(self.oauth_permissions)},),
        )

    def _user(self, conn, label):
        return fetch_one(
            conn,
            "INSERT INTO users (email,password_hash,display_name) VALUES (%s,%s,%s) RETURNING id::text",
            (f"{label}-{self.suffix}@example.test", hash_password("password123"), label),
        )

    def _membership(self, conn, user_id, role):
        return fetch_one(
            conn,
            "INSERT INTO community_memberships (user_id,community_id,role) VALUES (%s,%s,%s) RETURNING id::text",
            (user_id, self.community["id"], role),
        )

    def _login(self, conn, client, user_id):
        token = create_session(conn, user_id, self.config)
        client.set_cookie(self.config.session_cookie_name, token)


if __name__ == "__main__":
    unittest.main()
