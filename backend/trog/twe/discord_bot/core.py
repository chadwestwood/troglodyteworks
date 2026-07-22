from dataclasses import dataclass
import re

from ..config import Config
from ..db import fetch_one
from ..services.adapters import adapter_for
from ..services.provider_resolution import (
    read_game_server_health,
    read_game_server_mods,
    read_game_server_players,
    resolve_game_server_provider,
)
from .authorization import authorize, resolve_guild


class DiscordBotConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GameServerRef:
    id: str
    name: str
    slug: str
    management_adapter: str


@dataclass(frozen=True)
class BotReply:
    text: str
    code: str


HELP_REPLY = BotReply(
    "**Here is what I can do**\n"
    "- `/server status` — check whether the connected server is ready\n"
    "- `/server players` — list active players\n"
    "- `/server count` — count active players\n"
    "- `/server mods` — list active mods by name\n"
    "- `/server settings` — show the combined server overview\n"
    "You can also mention me and ask the same questions naturally. Read access follows your Community's approved Trog permissions.",
    "server_help",
)


def parse_guild_game_server_map(raw_value: str | None) -> dict[str, str]:
    if not raw_value:
        return {}
    mapping = {}
    for item in raw_value.split(","):
        entry = item.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise DiscordBotConfigurationError("Discord guild mapping entries must use guild_id=game_server_id.")
        guild_id, game_server_id = entry.split("=", 1)
        guild_id = guild_id.strip()
        game_server_id = game_server_id.strip()
        if not guild_id or not game_server_id:
            raise DiscordBotConfigurationError("Discord guild mapping entries must include both IDs.")
        mapping[guild_id] = game_server_id
    return mapping


def should_respond(mentioned_user_ids: list[str], bot_user_id: str) -> bool:
    return str(bot_user_id) in {str(user_id) for user_id in mentioned_user_ids}


def is_directly_mentioned(message: str, mentioned_user_ids: list[str], bot_user_id: str) -> bool:
    if should_respond(mentioned_user_ids, bot_user_id):
        return True
    if re.search(rf"<@!?{re.escape(str(bot_user_id))}>", message):
        return True
    # Some Discord clients/autocomplete contexts can leave us with plain text
    # during local/manual runs. Accept an explicit @trog prefix as a fallback,
    # while still ignoring ordinary conversations that do not address the bot.
    return bool(re.search(r"(^|\s)@trog\b", message, flags=re.IGNORECASE))


def classify_intent(message: str) -> str | None:
    normalized = message.lower()
    # Normalize common Unicode punctuation from mobile/desktop clients.
    normalized = normalized.replace("\u2019", "'").replace("\u2018", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = re.sub(r"<@!?\d+>", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if re.search(r"\b(help|commands?|what can you do)\b", normalized):
        return "server_help"
    if re.search(r"\bmap\s+settings\b", normalized):
        return "server_settings"
    if re.search(r"\bmod(?:'s|s)?\b", normalized) and re.search(
        r"\b(installed|active|loaded|running|using|enabled|list)\b", normalized
    ):
        return "mod_list"
    if re.search(r"\b(server|genesis|ark)\b", normalized) and re.search(r"\b(up|online|running|status)\b", normalized):
        return "server_status"
    if re.search(r"\b(who(?:\s+is|'s)|anyone)\b", normalized) and re.search(r"\b(on|online|server|players?)\b", normalized):
        return "player_list"
    if re.search(r"\b(list|show|name)\b", normalized) and re.search(r"\b(players?|online)\b", normalized):
        return "player_list"
    if re.search(r"\b(how many|players?|online|count)\b", normalized) and re.search(r"\b(players?|online)\b", normalized):
        return "player_count"
    return None


def game_server_for_guild(conn, guild_id: str, guild_map: dict[str, str] | None = None) -> GameServerRef | None:
    if guild_map == {}:
        return None
    context = resolve_guild(conn, guild_id)
    if context:
        return GameServerRef(
            id=context.game_server_id,
            name=context.game_server_name,
            slug=context.game_server_slug,
            management_adapter=context.management_adapter,
        )
    guild_map = guild_map or {}
    game_server_id = guild_map.get(str(guild_id))
    if not game_server_id:
        return None
    row = fetch_one(
        conn,
        """
        SELECT id::text, name, slug, management_adapter
        FROM game_servers
        WHERE id = %s
        """,
        (game_server_id,),
    )
    if not row:
        raise DiscordBotConfigurationError("Configured Discord guild game server does not exist.")
    return GameServerRef(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        management_adapter=row["management_adapter"],
    )


def server_status_reply(game_server: GameServerRef | None, config: Config, health_provider=None) -> BotReply:
    if not game_server:
        return BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")

    adapter = adapter_for(game_server.management_adapter)
    if not adapter:
        return BotReply("I cannot check that server right now because its status service is unavailable.", "status_unavailable")

    try:
        health = health_provider(config) if health_provider else adapter.health(config)
    except Exception:
        return BotReply("I cannot check that server right now because its status service is unavailable.", "status_unavailable")

    overall = health.get("overall_status")
    checks = health.get("checks", [])
    if _status_service_unavailable(overall, checks):
        return BotReply("I cannot check that server right now because its status service is unavailable.", "status_unavailable")
    if overall in {"offline", "failed"}:
        return BotReply(f"{game_server.name} appears to be offline.", "server_offline")
    if overall == "ready":
        return BotReply(f"{game_server.name} is up and ready for players.", "server_up")
    if overall == "degraded":
        return BotReply(f"{game_server.name} is up, but one or more readiness checks are degraded.", "server_degraded")
    return BotReply("I cannot confidently determine the server status right now.", "status_unavailable")


def player_count_reply(game_server: GameServerRef | None, config: Config, health_provider=None, players_provider=None) -> BotReply:
    status = server_status_reply(game_server, config, health_provider=health_provider)
    if status.code in {"guild_not_connected", "server_offline"}:
        return status

    if not game_server:
        return BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")
    try:
        data = players_provider() if players_provider else _default_players_provider()
    except Exception:
        return BotReply("I cannot read the player count right now because the player service is unavailable.", "players_unavailable")

    players = data.get("players", [])
    count = len(players)
    if count == 1:
        return BotReply(f"There is 1 player online on {game_server.name}.", "player_count")
    return BotReply(f"There are {count} players online on {game_server.name}.", "player_count")


def player_list_reply(game_server: GameServerRef | None, config: Config, health_provider=None, players_provider=None) -> BotReply:
    status = server_status_reply(game_server, config, health_provider=health_provider)
    if status.code in {"guild_not_connected", "server_offline"}:
        return status

    if not game_server:
        return BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")
    try:
        data = players_provider() if players_provider else _default_players_provider()
    except Exception:
        return BotReply("I cannot read active players right now because the player service is unavailable.", "players_unavailable")

    players = data.get("players", [])
    if not players:
        return BotReply(f"No players are currently online on **{game_server.name}**.", "player_list")

    names = [str(player).strip() for player in players if str(player).strip()]
    count = len(names)
    count_label = "player" if count == 1 else "players"
    lines = "\n".join(f"- {name}" for name in names)
    return BotReply(
        f"**{game_server.name}** currently has **{count}** {count_label} online:\n{lines}",
        "player_list",
    )


def mod_list_reply(game_server: GameServerRef | None, config: Config, mods_provider=None) -> BotReply:
    if not game_server:
        return BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")
    adapter = adapter_for(game_server.management_adapter)
    provider = mods_provider or (getattr(adapter, "installed_mods", None) if adapter else None)
    if not provider:
        return BotReply("I cannot read the installed mods because that server does not expose a mod list.", "mods_unavailable")
    try:
        mods = provider(config)
    except Exception:
        return BotReply("I cannot read the installed mods right now because the mod service is unavailable.", "mods_unavailable")
    names = [str(mod.get("name") or "").strip() for mod in mods if str(mod.get("name") or "").strip()]
    if not names:
        return BotReply(f"**{game_server.name}** has no active mods configured.", "mod_list")
    lines = "\n".join(f"- {name}" for name in names)
    return BotReply(
        f"**{game_server.name}** has **{len(names)}** active mods configured:\n{lines}",
        "mod_list",
    )


def server_settings_reply(status: BotReply, players: BotReply, mods: BotReply) -> BotReply:
    return BotReply(
        "\n\n".join(
            (
                f"**Server status**\n{status.text}",
                f"**Online players**\n{players.text}",
                f"**Active mods**\n{mods.text}",
            )
        ),
        "server_settings",
    )


def respond_to_message(message: str, guild_id: str, conn, config: Config, guild_map: dict[str, str] | None = None) -> BotReply | None:
    intent = classify_intent(message)
    if not intent:
        return HELP_REPLY
    game_server = game_server_for_guild(conn, guild_id, guild_map)
    if intent == "server_settings":
        return server_settings_reply(
            server_status_reply(game_server, config),
            player_list_reply(game_server, config),
            mod_list_reply(game_server, config),
        )
    if intent == "server_status":
        return server_status_reply(game_server, config)
    if intent == "player_list":
        return player_list_reply(game_server, config)
    if intent == "player_count":
        return player_count_reply(game_server, config)
    if intent == "mod_list":
        return mod_list_reply(game_server, config)
    return None


def capability_for_intent(intent: str) -> str:
    return {
        "server_status": "instance.status.read",
        "player_count": "instance.players.count.read",
        "player_list": "instance.players.names.read",
        "mod_list": "instance.mods.names.read",
        "server_restart": "instance.restart.execute",
    }[intent]


def respond_to_request(intent: str, guild_id: str, channel_id: str, discord_user_id: str,
                       conn, config: Config, guild_map: dict[str, str] | None = None) -> BotReply:
    if intent == "server_help":
        return HELP_REPLY
    if intent == "server_settings":
        replies = [
            respond_to_request(read_intent, guild_id, channel_id, discord_user_id, conn, config, guild_map)
            for read_intent in ("server_status", "player_list", "mod_list")
        ]
        return server_settings_reply(*replies)

    capability = capability_for_intent(intent)
    decision = authorize(conn, guild_id, channel_id, discord_user_id, capability)
    if not decision.context and guild_map:
        # Temporary compatibility for read-only installations not migrated to PostgreSQL yet.
        if capability in {
            "instance.status.read",
            "instance.players.count.read",
            "instance.players.names.read",
            "instance.mods.names.read",
        }:
            game_server = game_server_for_guild(conn, guild_id, guild_map)
            health_provider, players_provider, mods_provider = _resolved_read_providers(conn, game_server, config, intent)
            return _read_reply(
                intent,
                game_server,
                config,
                health_provider=health_provider,
                players_provider=players_provider,
                mods_provider=mods_provider,
            )
    if not decision.allowed:
        if decision.reason == "guild_not_connected":
            return BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")
        if decision.reason == "channel_disabled":
            return BotReply("Trog is not enabled for that capability in this channel.", "channel_disabled")
        if capability.endswith(".read"):
            return BotReply("That read capability has not been approved for this Discord server.", "read_not_approved")
        return BotReply("You are not authorized to restart this server.", "restart_denied")
    if intent == "server_restart":
        return BotReply(
            "You are authorized for `instance.restart.execute`, but restart execution is not enabled yet.",
            "restart_authorized_not_enabled",
        )
    game_server = GameServerRef(
        id=decision.context.game_server_id,
        name=decision.context.game_server_name,
        slug=decision.context.game_server_slug,
        management_adapter=decision.context.management_adapter,
    )
    health_provider, players_provider, mods_provider = _resolved_read_providers(conn, game_server, config, intent)
    return _read_reply(
        intent,
        game_server,
        config,
        health_provider=health_provider,
        players_provider=players_provider,
        mods_provider=mods_provider,
    )


def _read_reply(
    intent: str,
    game_server: GameServerRef | None,
    config: Config,
    health_provider=None,
    players_provider=None,
    mods_provider=None,
) -> BotReply:
    if intent == "server_status":
        return server_status_reply(game_server, config, health_provider=health_provider)
    if intent == "player_list":
        return player_list_reply(
            game_server,
            config,
            health_provider=health_provider,
            players_provider=players_provider,
        )
    if intent == "mod_list":
        return mod_list_reply(game_server, config, mods_provider=mods_provider)
    return player_count_reply(
        game_server,
        config,
        health_provider=health_provider,
        players_provider=players_provider,
    )


def _uses_health(intent: str) -> bool:
    return intent in {"server_status", "player_count", "player_list"}


def _uses_players(intent: str) -> bool:
    return intent in {"player_count", "player_list"}


def _uses_mods(intent: str) -> bool:
    return intent == "mod_list"


def _resolved_read_providers(conn, game_server: GameServerRef | None, config: Config, intent: str):
    if not game_server or (not _uses_health(intent) and not _uses_players(intent) and not _uses_mods(intent)):
        return None, None, None
    resolution = resolve_game_server_provider(conn, game_server.id)
    conn.commit()
    health_provider = (
        (lambda _config: read_game_server_health(resolution, config))
        if _uses_health(intent)
        else None
    )
    players_provider = (
        (lambda: read_game_server_players(resolution, config))
        if _uses_players(intent)
        else None
    )
    mods_provider = (
        (lambda _config: read_game_server_mods(resolution, config))
        if _uses_mods(intent)
        else None
    )
    return health_provider, players_provider, mods_provider


def _status_service_unavailable(overall: str | None, checks: list[dict]) -> bool:
    if overall == "unknown":
        statuses = {check.get("status") for check in checks}
        return not statuses or statuses <= {"unknown", "not_configured", "pending"}
    return False


def _default_players_provider():
    from services.rcon import list_players

    return list_players()
