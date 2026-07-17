import base64
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token as google_id_token

from .security import hash_password

SUPPORTED_PROVIDERS = {"google", "discord"}
SUPPORTED_PURPOSES = {"login", "link"}
STATE_LIFETIME = timedelta(minutes=10)
DISCORD_USER_AGENT = "DiscordBot (https://troglodyteworks.com, 1.0)"
DISCORD_MANAGE_GUILD = 0x20
DISCORD_ADMINISTRATOR = 0x8


@dataclass(frozen=True)
class ExternalProfile:
    provider: str
    subject: str
    username: str | None = None
    email: str | None = None
    email_verified: bool | None = None
    managed_guilds: tuple[tuple[str, str, str], ...] = ()


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def hash_oauth_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_pkce_verifier() -> str:
    return secrets.token_urlsafe(64)


def pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def safe_redirect_path(value, default="/communities/") -> str:
    path = str(value or "").strip()
    if not path:
        return default
    if not path.startswith("/") or path.startswith("//") or "://" in path:
        return default
    return path


def authorization_url(provider: str, config, state: str, code_verifier: str, nonce: str | None = None) -> str:
    if provider == "google":
        if not config.google_client_id or not config.google_redirect_uri:
            raise OAuthConfigurationError("Google OAuth is not configured.")
        params = {
            "client_id": config.google_client_id,
            "redirect_uri": config.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
            "nonce": nonce,
            "prompt": "select_account",
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    if provider == "discord":
        if not config.discord_client_id or not config.discord_redirect_uri:
            raise OAuthConfigurationError("Discord OAuth is not configured.")
        params = {
            "client_id": config.discord_client_id,
            "redirect_uri": config.discord_redirect_uri,
            "response_type": "code",
            "scope": "identify email guilds",
            "state": state,
            "code_challenge": pkce_challenge(code_verifier),
            "code_challenge_method": "S256",
            "prompt": "consent",
        }
        return f"https://discord.com/api/oauth2/authorize?{urlencode(params)}"
    raise OAuthConfigurationError("Unsupported OAuth provider.")


def exchange_authorization_code(provider: str, code: str, code_verifier: str, config, nonce: str | None = None) -> ExternalProfile:
    test_profiles = getattr(config, "oauth_test_profiles", None)
    if test_profiles and provider in test_profiles and code in test_profiles[provider]:
        return test_profiles[provider][code]
    if provider == "google":
        return exchange_google_code(code, code_verifier, config, nonce)
    if provider == "discord":
        return exchange_discord_code(code, code_verifier, config)
    raise OAuthProviderError("Unsupported OAuth provider.")


def exchange_google_code(code: str, code_verifier: str, config, nonce: str | None = None) -> ExternalProfile:
    if not config.google_client_id or not config.google_client_secret or not config.google_redirect_uri:
        raise OAuthConfigurationError("Google OAuth is not configured.")
    token_response = post_form(
        "https://oauth2.googleapis.com/token",
        {
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": config.google_redirect_uri,
        },
    )
    encoded_id_token = token_response.get("id_token")
    if not encoded_id_token:
        raise OAuthProviderError("Google did not return an ID token.")
    try:
        payload = google_id_token.verify_oauth2_token(
            encoded_id_token,
            GoogleAuthRequest(),
            config.google_client_id,
        )
    except (GoogleAuthError, ValueError) as exc:
        raise OAuthProviderError("Google ID token verification failed.") from exc
    if nonce and payload.get("nonce") != nonce:
        raise OAuthProviderError("Google nonce was invalid.")
    subject = payload.get("sub")
    if not subject:
        raise OAuthProviderError("Google subject was missing.")
    return ExternalProfile(
        provider="google",
        subject=str(subject),
        username=payload.get("name"),
        email=payload.get("email"),
        email_verified=payload.get("email_verified"),
    )


def exchange_discord_code(code: str, code_verifier: str, config) -> ExternalProfile:
    if not config.discord_client_id or not config.discord_client_secret or not config.discord_redirect_uri:
        raise OAuthConfigurationError("Discord OAuth is not configured.")
    token_response = post_form(
        "https://discord.com/api/oauth2/token",
        {
            "client_id": config.discord_client_id,
            "client_secret": config.discord_client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": config.discord_redirect_uri,
        },
        {"User-Agent": DISCORD_USER_AGENT},
    )
    access_token = token_response.get("access_token")
    if not access_token:
        raise OAuthProviderError("Discord did not return an access token.")
    user = get_json(
        "https://discord.com/api/users/@me",
        {"Authorization": f"Bearer {access_token}", "User-Agent": DISCORD_USER_AGENT},
    )
    guilds = get_json(
        "https://discord.com/api/users/@me/guilds",
        {"Authorization": f"Bearer {access_token}", "User-Agent": DISCORD_USER_AGENT},
    )
    subject = user.get("id")
    if not subject or not isinstance(guilds, list):
        raise OAuthProviderError("Discord returned an invalid identity response.")
    return ExternalProfile(
        provider="discord",
        subject=str(subject),
        username=user.get("global_name") or user.get("username"),
        email=user.get("email"),
        email_verified=user.get("verified"),
        managed_guilds=discord_managed_guilds(guilds),
    )


def discord_managed_guilds(guilds: list[dict]) -> tuple[tuple[str, str, str], ...]:
    managed = []
    for guild in guilds:
        guild_id = str(guild.get("id") or "").strip()
        if not guild_id.isdigit() or len(guild_id) > 20:
            continue
        try:
            permissions = int(str(guild.get("permissions", "0")))
        except (TypeError, ValueError):
            permissions = 0
        if guild.get("owner"):
            source = "owner"
        elif permissions & DISCORD_ADMINISTRATOR:
            source = "administrator"
        elif permissions & DISCORD_MANAGE_GUILD:
            source = "manage_guild"
        else:
            continue
        managed.append((guild_id, str(guild.get("name") or "Discord server"), source))
    return tuple(sorted(managed, key=lambda item: (item[1].lower(), item[0])))


def post_form(url: str, payload: dict, headers: dict | None = None) -> dict:
    data = urlencode(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/x-www-form-urlencoded", **(headers or {})}
    request = Request(url, data=data, headers=request_headers)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthProviderError("OAuth provider request failed.") from exc


def get_json(url: str, headers: dict) -> dict:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OAuthProviderError("OAuth provider request failed.") from exc


def generated_unusable_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


class OAuthConfigurationError(RuntimeError):
    pass


class OAuthProviderError(RuntimeError):
    pass
