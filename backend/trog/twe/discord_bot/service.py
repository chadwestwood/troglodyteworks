import asyncio
import logging
import os

from ..config import load_config
from ..db import Database
from ..services.runtime_heartbeat import record_runtime_heartbeat
from .core import (
    BotReply,
    DiscordBotConfigurationError,
    HELP_REPLY,
    classify_intent,
    is_directly_mentioned,
    parse_guild_game_server_map,
    respond_to_request,
)

LOGGER = logging.getLogger("twe.discord_bot")

NO_RESULT_REPLY = BotReply(
    "I received your command, but I could not produce a result right now. Reason: no matching response was generated.",
    "no_result",
)


def main():
    logging.basicConfig(level=os.environ.get("TROG_DISCORD_LOG_LEVEL", "INFO"))
    config = load_config()
    token = os.environ.get("TROG_DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("TROG_DISCORD_BOT_TOKEN is required.")

    try:
        guild_map = parse_guild_game_server_map(os.environ.get("TROG_DISCORD_GUILD_GAME_SERVER_MAP"))
    except DiscordBotConfigurationError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        import discord
    except ModuleNotFoundError as exc:
        raise SystemExit("Install discord.py before running the Discord bot service.") from exc

    # Start from no Gateway privileges and enable only what Trog actually uses.
    # This avoids silently gaining new event access when discord.py changes its
    # defaults. Message content remains necessary for addressed natural-language
    # questions; members, presences, reactions, typing, and voice are not used.
    intents = discord.Intents.none()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    client = discord.Client(intents=intents)
    allowed_mentions = discord.AllowedMentions.none()
    tree = discord.app_commands.CommandTree(client)
    database = Database(config.database_url)

    server_group = discord.app_commands.Group(name="server", description="Inspect or administer the connected game server")

    @server_group.command(name="status", description="Show the connected server status")
    async def server_status(interaction):
        await handle_interaction(
            interaction, "server_status", database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    @server_group.command(name="players", description="List players on the connected server")
    async def server_players(interaction):
        await handle_interaction(
            interaction, "player_list", database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    @server_group.command(name="mods", description="List active mods on the connected server")
    async def server_mods(interaction):
        await handle_interaction(
            interaction, "mod_list", database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    @server_group.command(name="settings", description="Show status, players, and active mods")
    async def server_settings(interaction):
        await handle_interaction(
            interaction, "server_settings", database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    @server_group.command(name="restart", description="Request a server restart")
    async def server_restart(interaction):
        await handle_interaction(
            interaction, "server_restart", database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    tree.add_command(server_group)

    @client.event
    async def on_ready():
        guilds = [(str(guild.id), guild.name) for guild in client.guilds]
        LOGGER.info("Trog Discord bot connected as %s", client.user)
        LOGGER.info("Trog Discord bot can see %s guild(s): %s", len(guilds), guilds)
        heartbeat_task = getattr(client, "_twe_heartbeat_task", None)
        if heartbeat_task is None or heartbeat_task.done():
            client._twe_heartbeat_task = asyncio.create_task(
                worker_heartbeat_loop(client, database),
                name="trog-runtime-heartbeat",
            )
        await tree.sync()

    @client.event
    async def on_message(message):
        await handle_message(
            message, client.user, database, config, guild_map,
            allowed_mentions=allowed_mentions,
        )

    client.run(token)


async def worker_heartbeat_loop(client, database, interval_seconds=30, logger=LOGGER):
    while not client.is_closed():
        ready = client.is_ready()
        try:
            with database.connect() as conn:
                record_runtime_heartbeat(
                    conn,
                    "trog_worker",
                    "ready" if ready else "connecting",
                    {"guild_count": len(client.guilds) if ready else 0},
                )
        except Exception:
            logger.exception("Trog runtime heartbeat update failed")
        await asyncio.sleep(interval_seconds)


async def handle_message(
    message, bot_user, database, config, guild_map, logger=LOGGER, allowed_mentions=None,
):
    if not bot_user:
        logger.warning("Discord message ignored because bot user is not ready.")
        return False
    if message.author == bot_user:
        logger.debug("Discord message ignored because it was sent by Trog.")
        return False
    if not message.guild:
        logger.debug("Discord direct message ignored.")
        return False

    content = str(getattr(message, "content", "") or "")
    mentioned_ids = [str(user.id) for user in getattr(message, "mentions", [])]
    bot_user_id = str(bot_user.id)
    mentioned = is_directly_mentioned(content, mentioned_ids, bot_user_id)
    intent = classify_intent(content)

    logger.info(
        "Discord message received guild_id=%s channel_id=%s author_id=%s mentions_trog=%s intent=%s content_length=%s",
        message.guild.id,
        message.channel.id,
        message.author.id,
        mentioned,
        intent or "none",
        len(content),
    )

    # Discord sometimes gives us message content without a usable mention object,
    # even when the user typed/selects @trog. To avoid silent failures, answer
    # deterministic supported status/player questions even if mention detection fails.
    if not mentioned and not intent:
        return False

    try:
        if not intent:
            reply = HELP_REPLY
        else:
            with database.connect() as conn:
                reply = respond_to_request(
                    intent, str(message.guild.id), str(message.channel.id), str(message.author.id),
                    conn, config, guild_map,
                )
    except DiscordBotConfigurationError:
        logger.warning("Discord guild is not connected to a valid TWE game server guild_id=%s", message.guild.id)
        reply = BotReply("This Discord server is not connected to a Troglodyte Works game server yet.", "guild_not_connected")
    except Exception:
        logger.exception("Discord bot message handling failed guild_id=%s", message.guild.id)
        reply = BotReply(
            "I could not answer that right now because the status service is unavailable.",
            "status_unavailable",
        )

    if not reply:
        logger.warning(
            "Discord command produced no reply; sending fallback guild_id=%s intent=%s mentioned=%s",
            message.guild.id,
            intent or "none",
            mentioned,
        )
        reply = NO_RESULT_REPLY

    send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
    await message.channel.send(reply.text, **send_options)
    logger.info("Discord reply sent guild_id=%s response_code=%s", message.guild.id, reply.code)
    return True


async def handle_interaction(
    interaction, intent, database, config, guild_map, logger=LOGGER, allowed_mentions=None,
):
    guild_id = str(interaction.guild_id) if interaction.guild_id else ""
    channel_id = str(interaction.channel_id) if interaction.channel_id else ""
    author_id = str(interaction.user.id)
    # Provider reads can legitimately take longer than Discord's initial
    # interaction deadline. Acknowledge first, then deliver the result through
    # the follow-up webhook. Administrative responses stay private.
    ephemeral = intent == "server_restart"
    await interaction.response.defer(thinking=True, ephemeral=ephemeral)
    try:
        with database.connect() as conn:
            reply = respond_to_request(intent, guild_id, channel_id, author_id, conn, config, guild_map)
    except Exception:
        logger.exception("Discord interaction handling failed guild_id=%s intent=%s", guild_id, intent)
        reply = BotReply("I could not process that command right now.", "interaction_unavailable")
    logger.info(
        "Discord authorization result guild_id=%s channel_id=%s author_id=%s capability=%s response_code=%s",
        guild_id, channel_id, author_id, intent, reply.code,
    )
    send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
    await interaction.followup.send(reply.text, ephemeral=ephemeral, **send_options)
    return reply


if __name__ == "__main__":
    main()
