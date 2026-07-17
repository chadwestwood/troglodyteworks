import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe import discord_api
from twe.config import Config


class DiscordAPITests(unittest.TestCase):
    def test_managed_guild_accepts_only_discord_management_authority(self):
        guild_id = "123456789012345678"
        self.assertEqual(discord_api.managed_guild(({"id": guild_id, "owner": True},), guild_id)[1], "owner")
        self.assertEqual(discord_api.managed_guild(({"id": guild_id, "permissions": "8"},), guild_id)[1], "administrator")
        self.assertEqual(discord_api.managed_guild(({"id": guild_id, "permissions": "32"},), guild_id)[1], "manage_guild")
        self.assertIsNone(discord_api.managed_guild(({"id": guild_id, "permissions": "0"},), guild_id))
        self.assertIsNone(discord_api.managed_guild(({"id": "999", "owner": True},), guild_id))

    def test_exchange_reads_user_and_guilds_from_discord(self):
        original_post = discord_api.post_form
        original_get = discord_api.get_json
        calls = []
        try:
            def fake_post(url, payload, headers):
                calls.append((url, headers))
                return {"access_token": "oauth-token"}

            discord_api.post_form = fake_post

            def fake_get(url, headers):
                calls.append((url, headers))
                if url.endswith("/users/@me"):
                    return {"id": "111"}
                return [{"id": "222", "permissions": "32"}]

            discord_api.get_json = fake_get
            config = Config(
                database_url="postgresql://unused",
                discord_client_id="client",
                discord_client_secret="secret",
                discord_install_redirect_uri="https://example.test/api/v1/discord/oauth/callback",
            )
            result = discord_api.exchange_guild_authorization("code", "verifier", config)
        finally:
            discord_api.post_form = original_post
            discord_api.get_json = original_get
        self.assertEqual(result.user_id, "111")
        self.assertEqual(result.guilds[0]["id"], "222")
        self.assertEqual(calls[0][1]["User-Agent"], discord_api.DISCORD_USER_AGENT)
        self.assertEqual(calls[1][1]["Authorization"], "Bearer oauth-token")
        self.assertEqual(calls[1][1]["User-Agent"], discord_api.DISCORD_USER_AGENT)

    def test_provider_failure_becomes_discord_api_error(self):
        original_post = discord_api.post_form
        try:
            def fail_post(_url, _payload, _headers):
                raise discord_api.OAuthProviderError("provider rejected request")

            discord_api.post_form = fail_post
            config = Config(
                database_url="postgresql://unused",
                discord_client_id="client",
                discord_client_secret="secret",
                discord_install_redirect_uri="https://example.test/api/v1/discord/oauth/callback",
            )
            with self.assertRaises(discord_api.DiscordAPIError):
                discord_api.exchange_guild_authorization("code", "verifier", config)
        finally:
            discord_api.post_form = original_post

    def test_bot_installation_requires_matching_guild_from_bot_api(self):
        original_get = discord_api.get_json
        calls = []
        try:
            def fake_get(url, headers):
                calls.append((url, headers))
                return {"id": "222", "name": "LizzLive"}

            discord_api.get_json = fake_get
            config = Config(database_url="postgresql://unused", discord_bot_token="bot-token")
            guild = discord_api.installed_bot_guild("222", config)
        finally:
            discord_api.get_json = original_get
        self.assertEqual(guild["name"], "LizzLive")
        self.assertEqual(calls[0][1]["Authorization"], "Bot bot-token")
        self.assertEqual(calls[0][1]["User-Agent"], discord_api.DISCORD_USER_AGENT)


if __name__ == "__main__":
    unittest.main()
