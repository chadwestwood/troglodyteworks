import asyncio
import logging
import os
import re
import time
import uuid

from ..config import load_config
from ..db import Database, execute, fetch_one
from ..services.runtime_heartbeat import record_runtime_heartbeat
from ..services.provider_resolution import (
    read_game_server_configuration,
    read_game_server_health,
    read_game_server_settings,
    resolve_game_server_provider,
)
from ..services.provider_contracts import ProviderSetting, ProviderSettingsSnapshot
from ..services.world_configuration_registry import (
    load_verified_world_configuration,
    store_verified_world_configuration,
)
from ..services.trog_brain_gateway import build_trog_brain_gateway
from ..services.knowledge_gaps import (
    failure_category_for_response,
    schedule_failed_response,
)
from ..services.railway_minecraft import RailwayMinecraft
from ..trog_brain import TrogBrainRequest
from .authorization import (
    ADMINISTRATIVE_CAPABILITIES,
    PUBLIC_CAPABILITIES,
    authorize,
    resolve_guild,
)
from .core import (
    BotReply,
    DiscordBotConfigurationError,
    HELP_REPLY,
    classify_intent,
    extract_mod_reference,
    is_directly_mentioned,
    operation_request_from_message,
    parse_guild_game_server_map,
    respond_to_request,
)

LOGGER = logging.getLogger("twe.discord_bot")

NO_RESULT_REPLY = BotReply(
    "I received your command, but I could not produce a result right now. Reason: no matching response was generated.",
    "no_result",
)
DISCORD_MESSAGE_LIMIT = 1900
RESTART_WATCH_INITIAL_DELAY_SECONDS = 20
RESTART_WATCH_POLL_SECONDS = 15
RESTART_WATCH_TIMEOUT_SECONDS = 15 * 60
RESTART_READY_CONFIRMATION_SECONDS = 60
_RESTART_WATCH_TASKS = {}
_SETTING_STOP_WORDS = {
    "a", "an", "and", "are", "but", "change", "do", "does", "easy", "feels",
    "for", "how", "i", "is", "it", "make", "me", "my", "not", "of", "on",
    "recommend", "server", "setting", "settings", "should", "the", "this", "to",
    "too", "want", "what", "which", "world", "would", "you",
}
_SETTING_TOPIC_ALIASES = {
    "harvest": {"harvest", "harvesting", "gather", "gathering", "resource", "resources"},
    "tame": {"tame", "taming"},
    "breed": {"breed", "breeding", "mating", "hatch", "mature", "baby"},
    "experience": {"xp", "experience"},
    "difficulty": {"difficulty"},
    "damage": {"damage"},
    "player": {"player", "players"},
    "dino": {"dino", "dinos", "dinosaur", "creature", "creatures"},
    "structure": {"structure", "structures", "building"},
    "food": {"food", "hunger"},
    "water": {"water", "thirst"},
    "stamina": {"stamina"},
}
_SETTING_TOPIC_PRIORITIES = {
    # A breeding question spans the whole lifecycle. Keep mating, incubation,
    # maturation, and imprinting represented instead of returning whichever
    # alphabetically sorted Baby* settings happen to come first.
    "breed": (
        "MatingIntervalMultiplier",
        "MatingSpeedMultiplier",
        "EggHatchSpeedMultiplier",
        "BabyMatureSpeedMultiplier",
        "BabyCuddleIntervalMultiplier",
        "BabyFoodConsumptionSpeedMultiplier",
        "BabyImprintAmountMultiplier",
    ),
}


class DiscordRequestLimiter:
    def __init__(self, limit=8, window_seconds=30, clock=time.monotonic):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self.requests = {}

    def allow(self, guild_id: str, user_id: str) -> bool:
        now = self.clock()
        key = (str(guild_id), str(user_id))
        recent = [stamp for stamp in self.requests.get(key, []) if stamp > now - self.window_seconds]
        if len(recent) >= self.limit:
            self.requests[key] = recent
            return False
        recent.append(now)
        self.requests[key] = recent
        return True


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
    request_limiter = DiscordRequestLimiter()

    server_group = discord.app_commands.Group(name="server", description="Inspect or administer the connected game server")

    @server_group.command(name="status", description="Show the connected server status")
    async def server_status(interaction):
        await handle_interaction(
            interaction, "server_status", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="players", description="List players on the connected server")
    async def server_players(interaction):
        await handle_interaction(
            interaction, "player_list", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="count", description="Count players on the connected server")
    async def server_count(interaction):
        await handle_interaction(
            interaction, "player_count", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="mods", description="List active mods on the connected server")
    async def server_mods(interaction):
        await handle_interaction(
            interaction, "mod_list", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="settings", description="Show status, players, and active mods")
    async def server_settings(interaction):
        await handle_interaction(
            interaction, "server_settings", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="help", description="Show Trog's available server commands")
    async def server_help(interaction):
        await handle_interaction(
            interaction, "server_help", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
        )

    @server_group.command(name="restart", description="Request a server restart")
    async def server_restart(interaction, confirm: bool = False):
        await handle_interaction(
            interaction, "server_restart", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
            confirmed=confirm,
        )

    @server_group.command(name="add-mod", description="Add an ASA mod by exact CurseForge name or project ID")
    async def server_add_mod(interaction, mod: str, confirm: bool = False):
        await handle_interaction(
            interaction, "mod_add", database, config, guild_map,
            allowed_mentions=allowed_mentions,
            request_limiter=request_limiter,
            command_argument=mod,
            confirmed=confirm,
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
            request_limiter=request_limiter,
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
    request_limiter=None, brain_gateway=None,
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
    mentioned_role_ids = [str(role.id) for role in getattr(message, "role_mentions", [])]
    bot_member = getattr(message.guild, "me", None)
    bot_role_ids = [
        str(role.id)
        for role in getattr(bot_member, "roles", [])
        if bool(getattr(role, "managed", False)) or str(getattr(role, "name", "")).casefold() == "trog"
    ]
    bot_user_id = str(bot_user.id)
    mentioned = is_directly_mentioned(
        content,
        mentioned_ids,
        bot_user_id,
        mentioned_role_ids=mentioned_role_ids,
        bot_role_ids=bot_role_ids,
    )
    operation_request = operation_request_from_message(content)
    intent = operation_request.intent if operation_request else classify_intent(content)

    logger.info(
        "Discord message received guild_id=%s channel_id=%s author_id=%s mentions_trog=%s intent=%s content_length=%s",
        message.guild.id,
        message.channel.id,
        message.author.id,
        mentioned,
        intent or "none",
        len(content),
    )

    if not mentioned:
        return False

    if request_limiter and not request_limiter.allow(str(message.guild.id), str(message.author.id)):
        reply = BotReply(
            "You are asking me too quickly. Please wait a few seconds and try again.",
            "discord_rate_limited",
        )
        send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
        await message.channel.send(reply.text, **send_options)
        schedule_failed_response(
            database, content, intent=intent, response_code=reply.code,
            assistant_response=reply.text,
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
        )
        return True

    try:
        if not intent:
            reply = await answer_advisory_question(
                content,
                str(message.guild.id),
                str(message.channel.id),
                str(message.author.id),
                database,
                config,
                brain_gateway=brain_gateway,
            )
        else:
            with database.connect() as conn:
                reply = respond_to_request(
                    intent, str(message.guild.id), str(message.channel.id), str(message.author.id),
                    conn, config, guild_map,
                    command_argument=(
                        operation_request.argument
                        if operation_request
                        else extract_mod_reference(content)
                    ),
                    confirmed=bool(operation_request and operation_request.confirmed),
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

    failure_category = failure_category_for_response(reply.code, reply.text, content)
    if failure_category:
        schedule_failed_response(
            database,
            content,
            game_type="ark_survival_ascended",
            intent=intent or "advisory",
            response_code=reply.code,
            assistant_response=reply.text,
            failure_category=failure_category,
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
        )

    send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
    for chunk in split_discord_message(reply.text):
        await message.channel.send(chunk, **send_options)
    if reply.code == "restart_requested":
        schedule_restart_watch(
            message.channel,
            str(message.guild.id),
            str(message.channel.id),
            database,
            config,
            reply.operation_id,
            allowed_mentions=allowed_mentions,
            logger=logger,
        )
    logger.info("Discord reply sent guild_id=%s response_code=%s", message.guild.id, reply.code)
    return True


async def answer_advisory_question(
    request_text,
    guild_id,
    channel_id,
    discord_user_id,
    database,
    config,
    *,
    brain_gateway=None,
):
    """Route an addressed, non-command question through the scoped Trog Brain."""
    response_mode = _classify_brain_intent(request_text)
    correlation_id = str(uuid.uuid4())
    with database.connect() as conn:
        base_decision = authorize(
            conn,
            guild_id,
            channel_id,
            discord_user_id,
            "instance.settings.read",
        )
        if not base_decision.allowed or not base_decision.context:
            if base_decision.reason == "channel_unmapped":
                return BotReply(
                    "Trog is not connected to this Discord channel yet.",
                    "brain_channel_unmapped",
                )
            return BotReply(
                "This Discord server is not connected to a Troglodyte Works World yet.",
                "brain_world_not_connected",
            )

        context = base_decision.context
        if not context.instance_id:
            return BotReply(
                "This Discord channel is not routed to one specific World yet.",
                "brain_world_not_connected",
            )
        if response_mode == "guide":
            return BotReply(
                "I don’t have a verified guide for that yet, so I won’t guess. "
                "I’ve added this question for review.",
                "trog_brain_knowledge_gap",
            )
        provider_resolution = resolve_game_server_provider(
            conn,
            context.game_server_id,
            correlation_id=correlation_id,
        )
        effective_capabilities = []
        cached_settings_snapshot = None
        if context.instance_id:
            try:
                cached_settings_snapshot = load_verified_world_configuration(
                    conn,
                    context.instance_id,
                )
            except Exception as exc:
                LOGGER.warning(
                    "World settings snapshot load failed correlation_id=%s "
                    "instance_id=%s error=%s",
                    correlation_id,
                    context.instance_id,
                    type(exc).__name__,
                )
        for capability in sorted(PUBLIC_CAPABILITIES | ADMINISTRATIVE_CAPABILITIES):
            decision = (
                base_decision
                if capability == "instance.settings.read"
                else authorize(
                    conn,
                    guild_id,
                    channel_id,
                    discord_user_id,
                    capability,
                )
            )
            if decision.allowed:
                effective_capabilities.append(capability)

    try:
        if not provider_resolution:
            raise LookupError("No connected provider was resolved.")
        # Questions asking for current/factual settings must refresh from the
        # connected provider. A cached snapshot can contain seeded defaults
        # that look complete but do not reflect the live World.
        settings_snapshot = None if response_mode == "factual" else cached_settings_snapshot
        relevant_settings = ()
        if settings_snapshot:
            relevant_settings = _relevant_provider_settings(
                request_text,
                settings_snapshot.settings,
                limit=_factual_setting_limit(request_text) if response_mode == "factual" else 6,
            )
        if not relevant_settings:
            settings_snapshot = await asyncio.to_thread(
                read_game_server_settings,
                provider_resolution,
                config,
            )
            settings_snapshot = ProviderSettingsSnapshot(
                settings=settings_snapshot.settings,
                checked_at=settings_snapshot.checked_at,
            )
            if context.instance_id:
                provider_context = getattr(provider_resolution, "context", None)
                if provider_context is not None:
                    configuration_snapshot = await asyncio.to_thread(
                        read_game_server_configuration,
                        provider_resolution,
                        config,
                    )
                    with database.connect() as conn:
                        settings_snapshot = store_verified_world_configuration(
                            conn,
                            game_instance_id=context.instance_id,
                            provider_context=provider_context,
                            settings_snapshot=settings_snapshot,
                            configuration_snapshot=configuration_snapshot,
                        )
        relevant_settings = _relevant_provider_settings(
            request_text,
            settings_snapshot.settings,
            limit=_factual_setting_limit(request_text) if response_mode == "factual" else 6,
        )
        if not relevant_settings:
            raise LookupError("No relevant live settings were returned.")
    except Exception as exc:
        LOGGER.warning(
            "Verified World settings unavailable correlation_id=%s game_server_id=%s error=%s",
            correlation_id,
            context.game_server_id,
            type(exc).__name__,
        )
        return BotReply(
            "I can’t verify the relevant live settings for this World right now, "
            "so I won’t guess. Please try again shortly.",
            "brain_settings_unavailable",
        )

    if response_mode == "factual":
        return BotReply(
            _format_requested_settings(relevant_settings),
            "trog_brain_grounded_answer",
        )

    community_name = context.provider_community_name or context.game_server_name
    world_name = context.instance_name or context.game_server_name
    world_id = context.instance_id or context.game_server_id
    request = TrogBrainRequest.from_dict(
        {
            "user_id": discord_user_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "community_id": context.community_id,
            "community_name": community_name,
            "world_id": world_id,
            "world_name": world_name,
            "effective_capabilities": effective_capabilities,
            "request_text": request_text,
            "correlation_id": correlation_id,
            "grounding_facts": [
                "The connected game is ARK: Survival Ascended.",
                (
                    f"Verified live provider settings, checked at "
                    f"{settings_snapshot.checked_at}: "
                    + "; ".join(
                        f"{setting.path} = {setting.value}"
                        for setting in relevant_settings
                    )
                ),
                _brain_response_instruction(response_mode),
                (
                    "Do not use defaults or generic values. If the supplied live values "
                    "do not support an answer, say you cannot verify the setting."
                ),
            ],
            "citations": [],
        }
    )
    gateway = brain_gateway or build_trog_brain_gateway(config)
    response = await asyncio.to_thread(gateway.respond, request)
    if response.kind == "grounded_answer" and not _is_concise_brain_answer(response.message):
        return BotReply(
            "I couldn’t produce a concise, trustworthy answer for that yet. "
            "I’ve added it for review.",
            "trog_brain_answer_quality",
        )
    return BotReply(response.message, f"trog_brain_{response.kind}")


def _classify_brain_intent(request_text):
    text = str(request_text or "").lower()
    if re.search(r"\b(how do i|how to|walk me through|tutorial|instructions?)\b", text):
        return "guide"
    if re.search(r"\b(recommend|suggest|advice|too easy|too hard|what should)\b", text):
        return "recommendation"
    if re.search(r"\b(change|apply|set|update|increase|decrease)\b", text):
        return "action"
    if re.search(r"\b(current|show|list|what are|what is)\b", text) and re.search(
        r"\b(settings?|configuration|values?|multipliers?|rates?)\b", text
    ):
        return "factual"
    return "general"


def _format_requested_settings(settings):
    lines = ["Current settings:"]
    for setting in settings:
        assignment = _provider_setting_assignment(setting)
        name = assignment[0] if assignment else str(setting.path).split(".")[-1]
        name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name).replace("_", " ")
        value = assignment[1] if assignment else str(setting.value)
        lines.append(f"• {name}: {value}")
    return "\n".join(lines)


def _provider_setting_assignment(setting):
    match = re.search(
        r"(?:^|[\s;])([A-Za-z][A-Za-z0-9_]*)\s*=\s*([^\s,;]+)",
        str(setting.value or ""),
    )
    return (match.group(1), match.group(2)) if match else None


def _provider_setting_identity(setting):
    assignment = _provider_setting_assignment(setting)
    name = assignment[0] if assignment else str(setting.path).split(".")[-1]
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _provider_setting_authority(setting):
    path = str(setting.path or "").lower()
    if path.startswith("saved.ini."):
        return 6
    if path.startswith("saved."):
        return 5
    if any(marker in path for marker in ("game.ini", "gameusersettings", "config")):
        return 4
    if "game_specific" in path:
        return 2
    return 1


def _is_verified_provider_setting(setting):
    """Return whether a provider value came from saved World configuration.

    Nitrado's gameserver document also contains form schemas, examples, and
    defaults. Some of those metadata fields contain strings that look exactly
    like ``Name=Value`` assignments, so assignment syntax alone is not proof
    that a value is active on the World.
    """
    path = str(setting.path or "").lower()
    metadata_markers = (
        "default",
        "definition",
        "description",
        "example",
        "form",
        "help",
        "label",
        "maximum",
        "minimum",
        "option",
        "schema",
        "template",
    )
    if any(marker in path for marker in metadata_markers):
        return False
    return path.startswith("saved.") or any(
        marker in path
        for marker in (
            "config.game.ini",
            "config.gameusersettings.ini",
            "config_file",
            "configfile",
            "game.ini",
            "gameusersettings.ini",
        )
    )


def _brain_response_instruction(response_mode):
    if response_mode == "recommendation":
        return (
            "Response mode: recommendation. Give exactly one recommendation and one "
            "brief reason. Use no headings, no data dump, no next-step offer, and no "
            "more than 80 words. Include only live values needed for the answer."
        )
    if response_mode == "action":
        return (
            "Response mode: action. Return only the requested unexecuted action proposal. "
            "Do not claim it was executed. Use no headings and no more than 80 words."
        )
    return (
        f"Response mode: {response_mode}. Answer directly in no more than 80 words. "
        "Include only facts needed to answer the question. Do not offer an action."
    )


def _is_concise_brain_answer(message):
    text = str(message or "").strip()
    if not text or text.lower() in {"let's check it out.", "lets check it out."}:
        return False
    if len(text.split()) > 80:
        return False
    if sum(1 for line in text.splitlines() if line.lstrip().startswith(("•", "-", "*"))) > 4:
        return False
    banned = ("what to check", "what i'd try", "what i’d try", "what i see now", "next step")
    return not any(section in text.lower() for section in banned)


def _relevant_provider_settings(request_text, settings, *, limit=12):
    request_tokens = _expanded_setting_tokens(request_text)
    ranked = []
    for setting in settings:
        assignment = _provider_setting_assignment(setting)
        # Only values from a verified provider path are proof of the value
        # saved for this World. Nitrado returns config-file entries as
        # ``Name=Value`` but returns saved control-panel settings as a scalar
        # value whose setting name is the final path segment.
        if not _is_verified_provider_setting(setting):
            continue
        if assignment is not None:
            verified_name, verified_value = assignment
        else:
            verified_name = str(setting.path or "").split(".")[-1].strip()
            verified_value = str(setting.value or "").strip()
            if not verified_name or not verified_value:
                continue
        searchable = f"{setting.path} {verified_name}"
        setting_tokens = _expanded_setting_tokens(searchable)
        overlap = request_tokens & setting_tokens
        if not overlap:
            continue
        score = len(overlap)
        if any(token in searchable.lower() for token in request_tokens):
            score += 1
        # Normalize the verified assignment before it reaches prompts or
        # factual replies. This removes Nitrado's container path and preserves
        # only the setting name and the value actually saved in its config.
        verified_setting = ProviderSetting(path=verified_name, value=verified_value)
        ranked.append((score, _provider_setting_authority(setting), verified_setting))

    # Nitrado may return both a convenient summary value and the explicit value
    # saved in a config assignment. Keep only the most authoritative version of
    # each setting so a generic 1.0 cannot mask the World's real configuration.
    best_by_identity = {}
    for score, authority, setting in ranked:
        identity = _provider_setting_identity(setting)
        current = best_by_identity.get(identity)
        candidate = (score, authority, setting)
        if current is None or (score, authority) > (current[0], current[1]):
            best_by_identity[identity] = candidate
    ranked = sorted(
        best_by_identity.values(),
        key=lambda item: (-item[0], -item[1], str(item[2].path).lower()),
    )
    ranked_settings = [item[2] for item in ranked]

    prioritized = []
    seen_identities = set()
    for topic, preferred_names in _SETTING_TOPIC_PRIORITIES.items():
        if topic not in request_tokens:
            continue
        for preferred_name in preferred_names:
            preferred_compact = re.sub(r"[^a-z0-9]+", "", preferred_name.lower())
            for setting in ranked_settings:
                identity = _provider_setting_identity(setting)
                if preferred_compact != identity or identity in seen_identities:
                    continue
                prioritized.append(setting)
                seen_identities.add(identity)
                break

    for setting in ranked_settings:
        identity = _provider_setting_identity(setting)
        if identity in seen_identities:
            continue
        prioritized.append(setting)
        seen_identities.add(identity)
    return prioritized[:limit]


def _factual_setting_limit(request_text):
    request_tokens = _expanded_setting_tokens(request_text)
    return 7 if "breed" in request_tokens else 5


def _expanded_setting_tokens(value):
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(token) > 1 and token not in _SETTING_STOP_WORDS
    }
    expanded = set(tokens)
    compact = re.sub(r"[^a-z0-9]+", "", str(value).lower())
    for canonical, aliases in _SETTING_TOPIC_ALIASES.items():
        if any(alias in tokens or alias in compact for alias in aliases):
            expanded.add(canonical)
    return expanded


async def handle_interaction(
    interaction, intent, database, config, guild_map, logger=LOGGER, allowed_mentions=None,
    request_limiter=None, command_argument=None, confirmed=False,
):
    guild_id = str(interaction.guild_id) if interaction.guild_id else ""
    channel_id = str(interaction.channel_id) if interaction.channel_id else ""
    author_id = str(interaction.user.id)
    # Provider reads can legitimately take longer than Discord's initial
    # interaction deadline. Acknowledge first, then deliver the result through
    # the follow-up webhook. Administrative responses stay private.
    ephemeral = intent in {"server_restart", "mod_add"}
    await interaction.response.defer(thinking=True, ephemeral=ephemeral)
    if request_limiter and not request_limiter.allow(guild_id, author_id):
        reply = BotReply(
            "You are using Trog commands too quickly. Please wait a few seconds and try again.",
            "discord_rate_limited",
        )
        send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
        await interaction.followup.send(reply.text, ephemeral=True, **send_options)
        schedule_failed_response(
            database,
            f"/server {intent}",
            intent=intent,
            response_code=reply.code,
            assistant_response=reply.text,
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
        )
        return reply
    try:
        if intent == "server_help":
            reply = HELP_REPLY
        else:
            with database.connect() as conn:
                reply = respond_to_request(
                    intent, guild_id, channel_id, author_id, conn, config, guild_map,
                    command_argument=command_argument,
                    confirmed=confirmed,
                )
    except Exception:
        logger.exception("Discord interaction handling failed guild_id=%s intent=%s", guild_id, intent)
        reply = BotReply("I could not process that command right now.", "interaction_unavailable")
    logger.info(
        "Discord authorization result guild_id=%s channel_id=%s author_id=%s capability=%s response_code=%s",
        guild_id, channel_id, author_id, intent, reply.code,
    )
    failure_category = failure_category_for_response(
        reply.code,
        reply.text,
        f"/server {intent} {command_argument or ''}".strip(),
    )
    if failure_category:
        schedule_failed_response(
            database,
            f"/server {intent} {command_argument or ''}".strip(),
            game_type="ark_survival_ascended",
            intent=intent,
            response_code=reply.code,
            assistant_response=reply.text,
            failure_category=failure_category,
            guild_id=guild_id,
            channel_id=channel_id,
            author_id=author_id,
        )
    send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
    for chunk in split_discord_message(reply.text):
        await interaction.followup.send(chunk, ephemeral=ephemeral, **send_options)
    if reply.code == "restart_requested" and getattr(interaction, "channel", None) is not None:
        schedule_restart_watch(
            interaction.channel,
            guild_id,
            channel_id,
            database,
            config,
            reply.operation_id,
            allowed_mentions=allowed_mentions,
            logger=logger,
        )
    return reply


def schedule_restart_watch(
    channel, guild_id, channel_id, database, config, operation_id=None, *,
    allowed_mentions=None, logger=LOGGER,
):
    key = str(operation_id) if operation_id else (str(guild_id), str(channel_id))
    existing = _RESTART_WATCH_TASKS.get(key)
    if existing and not existing.done():
        logger.info(
            "Restart readiness watch already active operation_id=%s guild_id=%s channel_id=%s",
            operation_id or "unrecorded",
            guild_id,
            channel_id,
        )
        return existing
    task = asyncio.create_task(
        monitor_restart_until_ready(
            channel,
            str(guild_id),
            str(channel_id),
            database,
            config,
            operation_id=operation_id,
            allowed_mentions=allowed_mentions,
            logger=logger,
        ),
        name=f"trog-restart-watch-{operation_id or f'{guild_id}-{channel_id}'}",
    )
    _RESTART_WATCH_TASKS[key] = task
    task.add_done_callback(lambda completed: _RESTART_WATCH_TASKS.pop(key, None))
    return task


async def monitor_restart_until_ready(
    channel,
    guild_id,
    channel_id,
    database,
    config,
    *,
    operation_id=None,
    allowed_mentions=None,
    logger=LOGGER,
    initial_delay=RESTART_WATCH_INITIAL_DELAY_SECONDS,
    poll_interval=RESTART_WATCH_POLL_SECONDS,
    timeout=RESTART_WATCH_TIMEOUT_SECONDS,
    ready_confirmation_seconds=RESTART_READY_CONFIRMATION_SECONDS,
    sleep=asyncio.sleep,
    clock=time.monotonic,
    health_reader=None,
):
    """Notify the requesting channel once a restarted routed server is ready.

    The watcher waits to observe a non-ready state. If Nitrado completes the
    transition between polls, two ready readings after a minimum settling
    period are accepted instead, preventing an immediate false positive from
    the pre-restart status.
    """
    started_at = clock()
    saw_not_ready = False
    consecutive_ready = 0
    server_name = "The server"
    send_options = {"allowed_mentions": allowed_mentions} if allowed_mentions is not None else {}
    await sleep(initial_delay)
    while clock() - started_at < timeout:
        try:
            if health_reader is None:
                if operation_id:
                    server_name, health = await asyncio.to_thread(
                        _read_operation_health,
                        database,
                        config,
                        str(operation_id),
                    )
                else:
                    server_name, health = await asyncio.to_thread(
                        _read_routed_health,
                        database,
                        config,
                        str(guild_id),
                        str(channel_id),
                    )
            else:
                server_name, health = health_reader()
            ready = bool(health and health.get("overall_status") == "ready")
            if ready:
                consecutive_ready += 1
                settled = clock() - started_at >= ready_confirmation_seconds
                if saw_not_ready or (settled and consecutive_ready >= 2):
                    if operation_id and not await asyncio.to_thread(
                        _finish_restart_operation,
                        database,
                        str(operation_id),
                        ready=True,
                        message=f"{server_name} is ready for players.",
                    ):
                        raise LookupError("The restart operation is no longer awaiting verification.")
                    await channel.send(
                        f"**{server_name}** is back up and ready for players.",
                        **send_options,
                    )
                    logger.info(
                        "Restart readiness confirmed guild_id=%s channel_id=%s server=%s",
                        guild_id,
                        channel_id,
                        server_name,
                    )
                    return True
            else:
                saw_not_ready = True
                consecutive_ready = 0
        except Exception:
            # Provider/API unavailability is normal while a game server is
            # restarting. Keep polling without exposing implementation errors
            # in Discord.
            saw_not_ready = True
            consecutive_ready = 0
            logger.info(
                "Restart readiness check unavailable guild_id=%s channel_id=%s",
                guild_id,
                channel_id,
                exc_info=True,
            )
        await sleep(poll_interval)
    if operation_id:
        await asyncio.to_thread(
            _finish_restart_operation,
            database,
            str(operation_id),
            ready=False,
            message=f"{server_name} did not become ready before the verification timeout.",
        )
    await channel.send(
        f"I am still waiting for **{server_name}** to become ready. The restart may still be in progress; ask `@Trog is the server up?` for the latest status.",
        **send_options,
    )
    logger.warning("Restart readiness watch timed out guild_id=%s channel_id=%s", guild_id, channel_id)
    return False


def _finish_restart_operation(database, operation_id: str, *, ready: bool, message: str) -> bool:
    operation_status = "completed" if ready else "failed"
    operation_stage = "ready" if ready else "readiness_timeout"
    check_status = "passed" if ready else "failed"
    audit_action = (
        "discord.server_operation.completed"
        if ready
        else "discord.server_operation.failed"
    )
    with database.connect() as conn:
        operation = fetch_one(
            conn,
            """
            UPDATE server_operations
            SET status = %s, current_stage = %s, completed_at = now(), result_message = %s
            WHERE id = %s
              AND capability = 'instance.restart.execute'
              AND status = 'verifying'
            RETURNING id::text, requested_by::text, game_instance_id::text, capability
            """,
            (operation_status, operation_stage, message, operation_id),
        )
        if not operation:
            return False
        execute(
            conn,
            """
            UPDATE server_operation_checks
            SET status = %s, completed_at = now(), result_message = %s
            WHERE server_operation_id = %s
              AND name = 'restart_readiness'
              AND status IN ('pending', 'running')
            """,
            (check_status, message, operation_id),
        )
        execute(
            conn,
            """
            INSERT INTO audit_logs
                (user_id, community_id, action, target_type, target_id, details)
            SELECT so.requested_by, gs.community_id, %s, 'server_operation', so.id,
                   jsonb_build_object('capability', so.capability, 'stage', %s::text)
            FROM server_operations so
            JOIN game_instances gi ON gi.id = so.game_instance_id
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE so.id = %s
            """,
            (audit_action, operation_stage, operation_id),
        )
    return True


def _read_operation_health(database, config, operation_id):
    with database.connect() as conn:
        operation = fetch_one(
            conn,
            """
            SELECT gi.name AS instance_name,
                   gi.provider_instance_id,
                   gs.id::text AS game_server_id,
                   gs.name AS game_server_name,
                   gs.management_adapter
            FROM server_operations so
            JOIN game_instances gi ON gi.id = so.game_instance_id
            JOIN game_servers gs ON gs.id = gi.game_server_id
            WHERE so.id = %s
              AND so.capability = 'instance.restart.execute'
              AND so.status = 'verifying'
            """,
            (operation_id,),
        )
        if not operation:
            raise LookupError("The restart operation is no longer awaiting verification.")
        server_name = operation["instance_name"] or operation["game_server_name"]
        if operation["management_adapter"] == "railway":
            service_id = operation["provider_instance_id"]
            if not service_id:
                raise LookupError("The restart operation has no Railway service target.")
            return server_name, RailwayMinecraft(config).health(service_id)
        resolution = resolve_game_server_provider(
            conn,
            operation["game_server_id"],
            correlation_id=operation_id,
        )
        if not resolution:
            raise LookupError("The restart operation target no longer exists.")
        return server_name, read_game_server_health(resolution, config)


def _read_routed_health(database, config, guild_id, channel_id):
    with database.connect() as conn:
        context = resolve_guild(conn, guild_id, channel_id)
        if not context:
            raise LookupError("The Discord channel no longer has a routed game server.")
        resolution = resolve_game_server_provider(conn, context.game_server_id)
        if not resolution:
            raise LookupError("The routed game server no longer exists.")
        return context.game_server_name, read_game_server_health(resolution, config)


def split_discord_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    rendered = str(text or "").strip()
    if not rendered:
        return ["I could not produce a response right now."]
    chunks = []
    current = ""
    for line in rendered.splitlines():
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or ["I could not produce a response right now."]


if __name__ == "__main__":
    main()
