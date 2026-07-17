import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.oauth import (
    DISCORD_USER_AGENT,
    OAuthProviderError,
    exchange_discord_code,
    exchange_google_code,
    post_form,
)


class GoogleTokenVerificationTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            google_client_id="google-client",
            google_client_secret="google-secret",
            google_redirect_uri="https://example.test/api/v1/auth/google/callback",
        )

    @patch("twe.oauth.google_id_token.verify_oauth2_token")
    @patch("twe.oauth.post_form")
    def test_google_profile_comes_from_verified_id_token(self, post_form, verify_token):
        post_form.return_value = {"id_token": "signed-google-token"}
        verify_token.return_value = {
            "sub": "google-subject",
            "name": "Mattertrala",
            "email": "mattertrala@example.test",
            "email_verified": True,
            "nonce": "expected-nonce",
        }

        profile = exchange_google_code(
            "authorization-code",
            "pkce-verifier",
            self.config,
            nonce="expected-nonce",
        )

        self.assertEqual(profile.subject, "google-subject")
        self.assertEqual(profile.email, "mattertrala@example.test")
        verify_token.assert_called_once()
        self.assertEqual(verify_token.call_args.args[0], "signed-google-token")
        self.assertEqual(verify_token.call_args.args[2], "google-client")

    @patch("twe.oauth.google_id_token.verify_oauth2_token")
    @patch("twe.oauth.post_form")
    def test_invalid_google_signature_is_rejected(self, post_form, verify_token):
        post_form.return_value = {"id_token": "forged-google-token"}
        verify_token.side_effect = ValueError("signature verification failed")

        with self.assertRaises(OAuthProviderError):
            exchange_google_code("authorization-code", "pkce-verifier", self.config)

    @patch("twe.oauth.google_id_token.verify_oauth2_token")
    @patch("twe.oauth.post_form")
    def test_google_nonce_must_match_verified_claims(self, post_form, verify_token):
        post_form.return_value = {"id_token": "signed-google-token"}
        verify_token.return_value = {"sub": "google-subject", "nonce": "wrong-nonce"}

        with self.assertRaises(OAuthProviderError):
            exchange_google_code(
                "authorization-code",
                "pkce-verifier",
                self.config,
                nonce="expected-nonce",
            )


class DiscordHttpClientTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            discord_client_id="discord-client",
            discord_client_secret="discord-secret",
            discord_redirect_uri="https://example.test/api/v1/auth/discord/callback",
        )

    @patch("twe.oauth.get_json")
    @patch("twe.oauth.post_form")
    def test_discord_requests_identify_the_http_client(self, post_form_mock, get_json_mock):
        post_form_mock.return_value = {"access_token": "discord-access-token"}
        get_json_mock.side_effect = [
            {"id": "123", "username": "Mattertrala"},
            [
                {"id": "333", "name": "Owned Guild", "owner": True, "permissions": "0"},
                {"id": "222", "name": "Managed Guild", "owner": False, "permissions": "32"},
                {"id": "444", "name": "Member Guild", "owner": False, "permissions": "0"},
            ],
        ]

        profile = exchange_discord_code("authorization-code", "pkce-verifier", self.config)

        self.assertEqual(post_form_mock.call_args.args[2]["User-Agent"], DISCORD_USER_AGENT)
        self.assertEqual(get_json_mock.call_count, 2)
        self.assertTrue(all(call.args[1]["User-Agent"] == DISCORD_USER_AGENT for call in get_json_mock.call_args_list))
        self.assertEqual(
            profile.managed_guilds,
            (
                ("222", "Managed Guild", "manage_guild"),
                ("333", "Owned Guild", "owner"),
            ),
        )

    @patch("twe.oauth.urlopen")
    def test_provider_http_error_becomes_oauth_provider_error(self, urlopen_mock):
        urlopen_mock.side_effect = HTTPError(
            "https://discord.com/api/oauth2/token",
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

        with self.assertRaises(OAuthProviderError):
            post_form("https://discord.com/api/oauth2/token", {"code": "invalid"})


if __name__ == "__main__":
    unittest.main()
