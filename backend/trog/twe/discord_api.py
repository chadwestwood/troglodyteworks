from dataclasses import dataclass
from urllib.error import HTTPError, URLError

from .oauth import DISCORD_USER_AGENT, OAuthProviderError, get_json, post_form


MANAGE_GUILD = 0x20
ADMINISTRATOR = 0x8


class DiscordAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiscordOAuthResult:
    user_id: str
    guilds: tuple[dict, ...]


def exchange_guild_authorization(code: str, code_verifier: str, config) -> DiscordOAuthResult:
    if not config.discord_client_id or not config.discord_client_secret or not config.discord_install_redirect_uri:
        raise DiscordAPIError("Discord guild authorization is not configured.")
    try:
        token = post_form(
            "https://discord.com/api/oauth2/token",
            {
                "client_id": config.discord_client_id,
                "client_secret": config.discord_client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": config.discord_install_redirect_uri,
            },
            {"User-Agent": DISCORD_USER_AGENT},
        )
        access_token = token.get("access_token")
        if not access_token:
            raise DiscordAPIError("Discord did not return an access token.")
        headers = {"Authorization": f"Bearer {access_token}", "User-Agent": DISCORD_USER_AGENT}
        user = get_json("https://discord.com/api/users/@me", headers)
        guilds = get_json("https://discord.com/api/users/@me/guilds", headers)
    except (HTTPError, URLError, TimeoutError, ValueError, OAuthProviderError) as exc:
        raise DiscordAPIError("Discord guild authorization failed.") from exc
    if not user.get("id") or not isinstance(guilds, list):
        raise DiscordAPIError("Discord returned an invalid guild authorization response.")
    return DiscordOAuthResult(user_id=str(user["id"]), guilds=tuple(guilds))


def managed_guild(guilds: tuple[dict, ...], guild_id: str) -> tuple[dict, str] | None:
    for guild in guilds:
        if str(guild.get("id")) != str(guild_id):
            continue
        owner = bool(guild.get("owner"))
        try:
            permissions = int(str(guild.get("permissions", "0")))
        except (TypeError, ValueError):
            permissions = 0
        if owner:
            return guild, "owner"
        if permissions & ADMINISTRATOR:
            return guild, "administrator"
        if permissions & MANAGE_GUILD:
            return guild, "manage_guild"
        return None
    return None


def installed_bot_guild(guild_id: str, config) -> dict:
    if not config.discord_bot_token:
        raise DiscordAPIError("The Trog bot token is not configured.")
    try:
        guild = get_json(
            f"https://discord.com/api/v10/guilds/{guild_id}",
            {"Authorization": f"Bot {config.discord_bot_token}", "User-Agent": DISCORD_USER_AGENT},
        )
    except (HTTPError, URLError, TimeoutError, ValueError, OAuthProviderError) as exc:
        raise DiscordAPIError("Trog is not installed in the selected Discord server.") from exc
    if str(guild.get("id")) != str(guild_id):
        raise DiscordAPIError("Discord returned the wrong installed server.")
    return guild
