from dataclasses import dataclass
import re

from ..config import Config
from ..db import execute, fetch_all, fetch_one
from ..services.adapters import adapter_for
from ..services.provider_resolution import (
    read_game_server_health,
    read_game_server_mods,
    read_game_server_players,
    resolve_game_server_provider,
)
from ..services.nitrado_provider import NitradoProvider, NitradoProviderError
from ..services.railway_minecraft import RailwayMinecraft, RailwayMinecraftError
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
    "- `/server add-mod <mod ID>` — add an ASA mod (owner/admin)\n"
    "- `/server restart` — restart the routed server (owner/admin)\n"
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


def is_directly_mentioned(
    message: str,
    mentioned_user_ids: list[str],
    bot_user_id: str,
    mentioned_role_ids: list[str] | None = None,
    bot_role_ids: list[str] | None = None,
) -> bool:
    if should_respond(mentioned_user_ids, bot_user_id):
        return True
    if re.search(rf"<@!?{re.escape(str(bot_user_id))}>", message):
        return True
    # Discord commonly presents the bot's managed integration role as
    # ``@Trog``. Role mentions are not included in ``message.mentions``, so
    # validate them against roles actually assigned to this bot member.
    if set(mentioned_role_ids or ()) & set(bot_role_ids or ()):
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
    if re.search(r"\b(add|install|enable)\b", normalized) and re.search(r"\bmod\b|\b\d{3,12}\b", normalized):
        return "mod_add"
    if re.search(r"\brestart\b", normalized):
        return "server_restart"
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


def extract_mod_id(message: str) -> str | None:
    normalized = re.sub(r"<@!?\d+>", " ", message)
    match = re.search(r"\b(?:add|install|enable)\b.*?\b(\d{3,12})\b", normalized, flags=re.IGNORECASE)
    return match.group(1) if match else None


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
    if not adapter and not health_provider:
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
        "mod_add": "instance.mods.write",
        "server_restart": "instance.restart.execute",
    }[intent]


def respond_to_request(intent: str, guild_id: str, channel_id: str, discord_user_id: str,
                       conn, config: Config, guild_map: dict[str, str] | None = None,
                       command_argument: str | None = None) -> BotReply:
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
        if decision.reason == "channel_unmapped":
            return BotReply("This channel is not assigned to a hosted game yet. Ask a Discord administrator to choose which server Trog should use here.", "channel_unmapped")
        if decision.reason == "channel_disabled":
            return BotReply("Trog is not enabled for that capability in this channel.", "channel_disabled")
        if capability.endswith(".read"):
            return BotReply("That read capability has not been approved for this Discord server.", "read_not_approved")
        return BotReply("Only an authorized Community owner or administrator can change or restart this server.", "administrative_denied")
    if intent == "mod_add":
        if not command_argument or not re.fullmatch(r"\d{3,12}", command_argument):
            return BotReply("Give me the numeric CurseForge mod ID, for example: `@Trog add 123456 to the map`.", "mod_id_required")
        return _execute_nitrado_operation(conn, decision, config, "instance.mods.write", command_argument)
    if intent == "server_restart":
        return _execute_nitrado_operation(conn, decision, config, "instance.restart.execute")
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


def _execute_provider_operation(conn, decision, config: Config, capability: str, argument: str | None = None) -> BotReply:
    context = decision.context
    resolution = resolve_game_server_provider(conn, context.game_server_id)
    if context.management_adapter == "railway" and capability == "instance.restart.execute":
        return _execute_railway_restart(conn, decision, config)
    if not resolution or resolution.mode != "provider" or resolution.context.connection.provider_key != "nitrado":
        return BotReply("That operation is not available for this hosting provider yet.", "provider_write_unavailable")
    instance_id = context.instance_id
    if not instance_id:
        instances = fetch_all(
            conn,
            "SELECT id::text FROM game_instances WHERE game_server_id = %s ORDER BY sort_order, created_at LIMIT 2",
            (context.game_server_id,),
        )
        # Administrative operations must never guess between maps. A channel
        # route supplies an exact instance; this fallback is only safe for a
        # legacy game server that has exactly one instance.
        instance_id = instances[0]["id"] if len(instances) == 1 else None
    if not instance_id:
        return BotReply("I could not identify the routed game instance for this operation.", "instance_unavailable")
    operation = fetch_one(
        conn,
        """
        INSERT INTO server_operations
            (game_instance_id, requested_by, capability, status, current_stage, started_at)
        VALUES (%s, %s, %s, 'executing', 'provider_request', now())
        RETURNING id::text
        """,
        (instance_id, decision.identity.user_id, capability),
    )
    provider = NitradoProvider(config)
    try:
        if capability == "instance.mods.write":
            added, mods = provider.add_mod(resolution.context, argument)
            if not added:
                message = f"Mod `{argument}` is already configured on **{context.game_server_name}**."
                code = "mod_already_installed"
            else:
                name = next((mod["name"] for mod in mods if mod["id"] == argument), f"Mod {argument}")
                message = (
                    f"Added **{name}** (`{argument}`) to **{context.game_server_name}**. "
                    "The setting is saved; use `@Trog restart` in this channel when you are ready to apply it."
                )
                code = "mod_added"
        else:
            provider.restart(resolution.context)
            message = (
                f"Nitrado accepted the restart request for **{context.game_server_name}**. "
                "It may take several minutes to return. I will let this channel know when it is ready for players."
            )
            code = "restart_requested"
        execute(
            conn,
            "UPDATE server_operations SET status = 'completed', current_stage = 'provider_accepted', completed_at = now(), result_message = %s WHERE id = %s",
            (message, operation["id"]),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id, details)
            VALUES (%s, %s, %s, 'server_operation', %s, jsonb_build_object('capability', %s::text, 'argument', %s::text))
            """,
            (decision.identity.user_id, context.community_id, "discord.server_operation.completed", operation["id"], capability, argument),
        )
        return BotReply(message, code)
    except (NitradoProviderError, ValueError) as exc:
        safe_message = str(exc)[:400]
        execute(
            conn,
            "UPDATE server_operations SET status = 'failed', current_stage = 'failed', completed_at = now(), result_message = %s WHERE id = %s",
            (safe_message, operation["id"]),
        )
        return BotReply(f"I could not complete that Nitrado operation: {safe_message}", "provider_operation_failed")


# Compatibility name retained for tests and callers that exercise the Nitrado path directly.
def _execute_nitrado_operation(conn, decision, config: Config, capability: str, argument: str | None = None) -> BotReply:
    return _execute_provider_operation(conn, decision, config, capability, argument)


def _execute_railway_restart(conn, decision, config: Config) -> BotReply:
    context = decision.context
    instance_id, service_id = _railway_target(conn, context)
    if not instance_id or not service_id:
        return BotReply("I could not identify the routed Minecraft world for this operation.", "instance_unavailable")
    operation = fetch_one(
        conn,
        """
        INSERT INTO server_operations
            (game_instance_id, requested_by, capability, status, current_stage, started_at)
        VALUES (%s, %s, 'instance.restart.execute', 'executing', 'provider_request', now())
        RETURNING id::text
        """,
        (instance_id, decision.identity.user_id),
    )
    try:
        RailwayMinecraft(config).deploy(service_id)
        message = (
            f"Railway accepted the restart request for **{context.game_server_name}**. "
            "It may take several minutes to return. I will let this channel know when it is ready for players."
        )
        execute(
            conn,
            "UPDATE server_operations SET status='completed',current_stage='provider_accepted',completed_at=now(),result_message=%s WHERE id=%s",
            (message, operation["id"]),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs (user_id,community_id,action,target_type,target_id,details)
            VALUES (%s,%s,'discord.server_operation.completed','server_operation',%s,
                    jsonb_build_object('capability','instance.restart.execute'))
            """,
            (decision.identity.user_id, context.community_id, operation["id"]),
        )
        return BotReply(message, "restart_requested")
    except RailwayMinecraftError as error:
        safe_message = str(error)[:400]
        execute(
            conn,
            "UPDATE server_operations SET status='failed',current_stage='failed',completed_at=now(),result_message=%s WHERE id=%s",
            (safe_message, operation["id"]),
        )
        return BotReply(f"I could not complete that Railway operation: {safe_message}", "provider_operation_failed")


def _railway_target(conn, context):
    if context.instance_id:
        row = fetch_one(
            conn,
            "SELECT id::text,provider_instance_id FROM game_instances WHERE id=%s AND game_server_id=%s",
            (context.instance_id, context.game_server_id),
        )
        return (row["id"], row["provider_instance_id"]) if row else (None, None)
    rows = fetch_all(
        conn,
        "SELECT id::text,provider_instance_id FROM game_instances WHERE game_server_id=%s ORDER BY sort_order,created_at LIMIT 2",
        (context.game_server_id,),
    )
    return (rows[0]["id"], rows[0]["provider_instance_id"]) if len(rows) == 1 else (None, None)


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
    railway_service_id = None
    if game_server.management_adapter == "railway":
        rows = fetch_all(
            conn,
            "SELECT provider_instance_id FROM game_instances WHERE game_server_id=%s ORDER BY sort_order,created_at LIMIT 2",
            (game_server.id,),
        )
        railway_service_id = rows[0]["provider_instance_id"] if len(rows) == 1 else None
    conn.commit()
    health_provider = (
        (lambda _config: RailwayMinecraft(config).health(railway_service_id))
        if _uses_health(intent) and railway_service_id
        else (lambda _config: read_game_server_health(resolution, config))
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
