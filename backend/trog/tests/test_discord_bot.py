import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.discord_bot.core import (
    BotReply,
    DiscordBotConfigurationError,
    GameServerRef,
    classify_intent,
    extract_mod_id,
    is_directly_mentioned,
    parse_guild_game_server_map,
    respond_to_message,
    respond_to_request,
    player_count_reply,
    player_list_reply,
    mod_list_reply,
    server_settings_reply,
    server_status_reply,
    should_respond,
)
from twe.discord_bot.authorization import (
    AuthorizationDecision,
    DiscordContext,
    DiscordIdentity,
    authorize,
    channel_enabled,
    resolve_identity,
)
from twe.discord_bot.service import (
    DiscordRequestLimiter,
    handle_interaction,
    handle_message,
    split_discord_message,
)


class DiscordBotCoreTests(unittest.TestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")
        self.server = GameServerRef(
            id="00000000-0000-0000-0000-000000000001",
            name="Cohorts in the Wild",
            slug="ark-survival-ascended",
            management_adapter="local_asa",
        )

    def test_direct_mention_required(self):
        self.assertTrue(should_respond(["123", "456"], "456"))
        self.assertFalse(should_respond(["123"], "456"))
        self.assertTrue(is_directly_mentioned("<@456> hello", [], "456"))
        self.assertTrue(is_directly_mentioned("<@!456> hello", [], "456"))
        self.assertTrue(is_directly_mentioned("@Trog hello", [], "456"))
        self.assertFalse(is_directly_mentioned("Trog hello", [], "456"))

    def test_classifies_supported_intents_without_llm(self):
        self.assertEqual(classify_intent("<@123> is the server up?"), "server_status")
        self.assertEqual(classify_intent("<@123> how many players are online?"), "player_count")
        self.assertEqual(classify_intent("<@123> who's on?"), "player_list")
        self.assertEqual(classify_intent("<@123> who's on the server"), "player_list")
        self.assertEqual(classify_intent("<@123> who’s on?"), "player_list")
        self.assertEqual(classify_intent("<@123> is anyone on the server?"), "player_list")
        self.assertEqual(classify_intent("<@123> is anyone online"), "player_list")
        self.assertEqual(classify_intent("@trog list online players"), "player_list")
        self.assertEqual(classify_intent("<@123> show online players"), "player_list")
        self.assertEqual(classify_intent("@trog map settings"), "server_settings")
        self.assertEqual(classify_intent("<@123> show map settings"), "server_settings")
        self.assertIsNone(classify_intent("@trog server settings"))
        self.assertEqual(classify_intent("<@123> what mods are installed?"), "mod_list")
        self.assertEqual(classify_intent("<@123> what mod's are installed?"), "mod_list")
        self.assertEqual(classify_intent("<@123> list active mods"), "mod_list")
        self.assertEqual(classify_intent("<@123> add 123456 to the map"), "mod_add")
        self.assertEqual(classify_intent("@trog install mod 987654"), "mod_add")
        self.assertEqual(classify_intent("@trog restart"), "server_restart")
        self.assertEqual(classify_intent("<@123> help"), "server_help")
        self.assertEqual(classify_intent("<@123> what can you do?"), "server_help")
        self.assertIsNone(classify_intent("<@123> tell me a joke"))

    def test_extracts_only_numeric_mod_id_from_add_command(self):
        self.assertEqual(extract_mod_id("<@123> add 987654 to the map"), "987654")
        self.assertEqual(extract_mod_id("@Trog install mod 123456"), "123456")
        self.assertIsNone(extract_mod_id("@Trog add this mod"))

    def test_bot_managed_role_mention_is_treated_as_direct_mention(self):
        self.assertTrue(
            is_directly_mentioned(
                "<@&456> is the server up?",
                [],
                "123",
                mentioned_role_ids=["456"],
                bot_role_ids=["456"],
            )
        )
        self.assertFalse(
            is_directly_mentioned(
                "<@&999> is the server up?",
                [],
                "123",
                mentioned_role_ids=["999"],
                bot_role_ids=["456"],
            )
        )

    def test_worker_registers_combined_server_settings_command(self):
        service_source = (ROOT / "twe" / "discord_bot" / "service.py").read_text()
        self.assertIn('@server_group.command(name="settings"', service_source)
        self.assertIn('interaction, "server_settings"', service_source)
        self.assertIn('@server_group.command(name="count"', service_source)
        self.assertIn('@server_group.command(name="help"', service_source)
        self.assertIn('@server_group.command(name="add-mod"', service_source)

    def test_long_discord_responses_are_split_within_platform_limit(self):
        text = "\n".join(f"- Mod {index}: " + ("x" * 300) for index in range(20))

        chunks = split_discord_message(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1900 for chunk in chunks))
        self.assertEqual("\n".join(chunks), text)

    def test_parse_guild_mapping(self):
        mapping = parse_guild_game_server_map("111=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa,222=bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        self.assertEqual(mapping["111"], "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        self.assertEqual(mapping["222"], "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
        with self.assertRaises(DiscordBotConfigurationError):
            parse_guild_game_server_map("111")

    def test_guild_not_connected_response(self):
        reply = server_status_reply(None, self.config)
        self.assertEqual(reply.code, "guild_not_connected")
        self.assertIn("not connected", reply.text)

    def test_supported_status_question_without_guild_mapping(self):
        reply = respond_to_message("<@123> is the server up?", "111", object(), self.config, {})
        self.assertEqual(reply.code, "guild_not_connected")

    def test_unsupported_question_gets_help_response(self):
        reply = respond_to_message("<@123> hello", "111", object(), self.config, {})
        self.assertEqual(reply.code, "server_help")
        self.assertIn("/server status", reply.text)

    def test_server_offline_response(self):
        reply = server_status_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "offline",
                "checks": [{"name": "process_running", "status": "failed"}],
            },
        )
        self.assertEqual(reply.code, "server_offline")

    def test_status_service_unavailable_response(self):
        reply = server_status_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "unknown",
                "checks": [{"name": "process_running", "status": "not_configured"}],
            },
        )
        self.assertEqual(reply.code, "status_unavailable")

    def test_server_ready_response(self):
        reply = server_status_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "ready",
                "checks": [{"name": "process_running", "status": "passed"}],
            },
        )
        self.assertEqual(reply.code, "server_up")

    def test_player_count_response(self):
        reply = player_count_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "ready",
                "checks": [{"name": "process_running", "status": "passed"}],
            },
            players_provider=lambda: {"players": ["A", "B", "C"]},
        )
        self.assertEqual(reply.code, "player_count")
        self.assertIn("3 players", reply.text)

    def test_player_count_does_not_hide_offline_status(self):
        reply = player_count_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "offline",
                "checks": [{"name": "process_running", "status": "failed"}],
            },
            players_provider=lambda: {"players": ["A"]},
        )
        self.assertEqual(reply.code, "server_offline")

    def test_player_list_response_with_active_users(self):
        reply = player_list_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "ready",
                "checks": [{"name": "process_running", "status": "passed"}],
            },
            players_provider=lambda: {"players": ["A", "B"]},
        )
        self.assertEqual(reply.code, "player_list")
        self.assertIn("currently has **2** players online", reply.text)
        self.assertIn("- A", reply.text)
        self.assertIn("- B", reply.text)

    def test_player_list_response_without_active_users(self):
        reply = player_list_reply(
            self.server,
            self.config,
            health_provider=lambda _config: {
                "overall_status": "ready",
                "checks": [{"name": "process_running", "status": "passed"}],
            },
            players_provider=lambda: {"players": []},
        )
        self.assertEqual(reply.code, "player_list")
        self.assertIn("No players are currently online", reply.text)
        self.assertIn("**Cohorts in the Wild**", reply.text)

    def test_mod_list_response_uses_names_in_launch_order(self):
        reply = mod_list_reply(
            self.server,
            self.config,
            mods_provider=lambda _config: [
                {"id": "1", "name": "First Mod"},
                {"id": "2", "name": "Second Mod"},
            ],
        )
        self.assertEqual(reply.code, "mod_list")
        self.assertIn("**2** active mods", reply.text)
        self.assertLess(reply.text.index("- First Mod"), reply.text.index("- Second Mod"))

    def test_mod_list_reports_provider_failure(self):
        def unavailable(_config):
            raise OSError("unavailable")

        reply = mod_list_reply(self.server, self.config, mods_provider=unavailable)
        self.assertEqual(reply.code, "mods_unavailable")

    def test_server_settings_combines_all_three_sections(self):
        reply = server_settings_reply(
            BotReply("Server is ready.", "server_up"),
            BotReply("- Player One", "player_list"),
            BotReply("- Mod One", "mod_list"),
        )

        self.assertEqual(reply.code, "server_settings")
        self.assertIn("**Server status**\nServer is ready.", reply.text)
        self.assertIn("**Online players**\n- Player One", reply.text)
        self.assertIn("**Active mods**\n- Mod One", reply.text)

    @patch(
        "twe.discord_bot.core._resolved_read_providers",
        return_value=(lambda _config: {}, lambda: {"players": []}, lambda _config: []),
    )
    @patch("twe.discord_bot.core._read_reply")
    @patch("twe.discord_bot.core.authorize")
    def test_server_settings_authorizes_each_read_capability(
        self, authorize_mock, read_reply_mock, _read_providers_mock
    ):
        authorize_mock.side_effect = lambda _conn, _guild, _channel, _user, capability: AuthorizationDecision(
            True, "authorized", capability, self._context(),
            DiscordIdentity("111", "user", "membership", "member"),
        )
        read_reply_mock.side_effect = [
            BotReply("Server is ready.", "server_up"),
            BotReply("- Player One", "player_list"),
            BotReply("- Mod One", "mod_list"),
        ]

        reply = respond_to_request("server_settings", "222", "333", "111", object(), self.config)

        self.assertEqual(reply.code, "server_settings")
        self.assertEqual(
            [call.args[-1] for call in authorize_mock.call_args_list],
            ["instance.status.read", "instance.players.names.read", "instance.mods.names.read"],
        )

    @patch("twe.discord_bot.core._execute_nitrado_operation")
    @patch("twe.discord_bot.core.authorize")
    def test_authorized_restart_is_executed(self, authorize_mock, execute_mock):
        authorize_mock.return_value = AuthorizationDecision(
            True, "authorized", "instance.restart.execute", self._context(),
            DiscordIdentity("111", "user", "membership", "owner"),
        )
        execute_mock.return_value = BotReply("Restart accepted.", "restart_requested")
        reply = respond_to_request("server_restart", "222", "333", "111", object(), self.config)
        self.assertEqual(reply.code, "restart_requested")
        execute_mock.assert_called_once()

    @patch("twe.discord_bot.core.authorize")
    def test_unauthorized_restart_is_denied(self, authorize_mock):
        authorize_mock.return_value = AuthorizationDecision(
            False, "capability_not_granted", "instance.restart.execute", self._context(),
            DiscordIdentity("111", "user", "membership", "member"),
        )
        reply = respond_to_request("server_restart", "222", "333", "111", object(), self.config)
        self.assertEqual(reply.code, "administrative_denied")

    def _context(self):
        return DiscordContext("installation", "222", "community", self.server.id,
                              self.server.name, self.server.slug, self.server.management_adapter)


class DiscordAuthorizationUnitTests(unittest.TestCase):
    @patch("twe.discord_bot.authorization.fetch_one")
    def test_identity_resolution_uses_immutable_discord_user_id(self, fetch_mock):
        fetch_mock.return_value = {"discord_user_id": "111", "user_id": "u", "membership_id": "m", "role": "owner"}
        identity = resolve_identity(object(), "111", "community")
        self.assertEqual(identity.discord_user_id, "111")
        self.assertEqual(identity.role, "owner")

    @patch("twe.discord_bot.authorization.fetch_one", return_value={"enabled": False})
    def test_channel_policy_can_disable_category(self, _fetch_mock):
        context = DiscordContext("installation", "222", "community", "server", "Server", "server", "local_asa")
        self.assertFalse(channel_enabled(object(), context, "333", "administrative"))

    @patch("twe.discord_bot.authorization.can_request_capability", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_owner_access_is_authorized(self, guild_mock, _channel_mock, identity_mock, _capability_mock):
        guild_mock.return_value = DiscordContext("installation", "222", "community", "server", "Server", "server", "local_asa")
        identity_mock.return_value = DiscordIdentity("111", "user", "membership", "owner")
        self.assertTrue(authorize(object(), "222", "333", "111", "instance.restart.execute").allowed)

    @patch("twe.discord_bot.authorization.can_request_capability", return_value=False)
    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_ordinary_member_without_grant_is_denied(self, guild_mock, _channel_mock, identity_mock, _capability_mock):
        guild_mock.return_value = DiscordContext("installation", "222", "community", "server", "Server", "server", "local_asa")
        identity_mock.return_value = DiscordIdentity("111", "user", "membership", "member")
        decision = authorize(object(), "222", "333", "111", "instance.restart.execute")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "capability_not_granted")

    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.grant_capability_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_unlinked_identity_is_denied_administrative_access(
        self, guild_mock, _channel_mock, _grant_mock, identity_mock,
    ):
        guild_mock.return_value = DiscordContext(
            "installation", "222", "community", "server", "Server", "server", "local_asa",
        )
        identity_mock.return_value = DiscordIdentity("111", None, None, None)

        decision = authorize(object(), "222", "333", "111", "instance.restart.execute")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "identity_not_linked")

    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.grant_capability_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_linked_identity_without_target_community_membership_is_denied(
        self, guild_mock, _channel_mock, _grant_mock, identity_mock,
    ):
        guild_mock.return_value = DiscordContext(
            "installation", "222", "target-community", "server", "Server", "server", "local_asa",
        )
        # The Discord account is linked globally, but has no membership in the
        # provider community resolved from this guild's installation.
        identity_mock.return_value = DiscordIdentity("111", "other-community-user", None, None)

        decision = authorize(object(), "222", "333", "111", "instance.restart.execute")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "not_a_community_member")

    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.grant_capability_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_unknown_administrative_capability_is_fail_closed(
        self, guild_mock, _channel_mock, _grant_mock, identity_mock,
    ):
        guild_mock.return_value = DiscordContext(
            "installation", "222", "community", "server", "Server", "server", "local_asa",
        )

        decision = authorize(object(), "222", "333", "111", "instance.delete.execute")

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "unknown_capability")
        identity_mock.assert_not_called()

    @patch("twe.discord_bot.authorization.can_request_capability", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_identity")
    @patch("twe.discord_bot.authorization.grant_capability_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.channel_enabled", return_value=True)
    @patch("twe.discord_bot.authorization.resolve_guild")
    def test_instance_target_is_preserved_during_capability_check(
        self, guild_mock, _channel_mock, _grant_mock, identity_mock, capability_mock,
    ):
        guild_mock.return_value = DiscordContext(
            "installation", "222", "community", "server", "Server", "server", "nitrado",
            instance_access_grant_id="discord-grant", instance_id="genesis-instance",
        )
        identity_mock.return_value = DiscordIdentity("111", "user", "membership", "member")

        decision = authorize(object(), "222", "333", "111", "instance.restart.execute")

        self.assertTrue(decision.allowed)
        access = capability_mock.call_args.args[0]
        self.assertEqual(access["game_server_id"], "server")
        self.assertEqual(access["instance_id"], "genesis-instance")


class DiscordBotMessageHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")
        self.bot = FakeUser(999)
        self.author = FakeUser(111)

    async def test_message_event_received_for_direct_unsupported_mention(self):
        message = FakeMessage(
            content="<@999> hello",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("/server status", message.channel.sent[0])

    async def test_message_reply_disables_generated_mentions(self):
        message = FakeMessage(
            content="<@999> hello",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        safe_mentions = object()

        handled = await handle_message(
            message, self.bot, FakeDatabase(), self.config, {},
            allowed_mentions=safe_mentions,
        )

        self.assertTrue(handled)
        self.assertIs(message.channel.last_send_options["allowed_mentions"], safe_mentions)

    async def test_ignores_supported_status_question_without_direct_mention(self):
        message = FakeMessage(
            content="is the server up?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertFalse(handled)
        self.assertEqual(message.channel.sent, [])

    async def test_answers_player_list_question_with_direct_mention(self):
        message = FakeMessage(
            content="<@999> who's on?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("not connected", message.channel.sent[0])

    async def test_ignores_player_list_question_without_direct_mention(self):
        message = FakeMessage(
            content="is anyone on the server?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertFalse(handled)
        self.assertEqual(message.channel.sent, [])

    async def test_rate_limits_repeated_mentions_per_user_and_guild(self):
        message = FakeMessage(
            content="<@999> help",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )
        limiter = DiscordRequestLimiter(limit=1, window_seconds=30, clock=lambda: 100)

        first = await handle_message(
            message, self.bot, FakeDatabase(), self.config, {}, request_limiter=limiter,
        )
        second = await handle_message(
            message, self.bot, FakeDatabase(), self.config, {}, request_limiter=limiter,
        )

        self.assertTrue(first)
        self.assertTrue(second)
        self.assertIn("too quickly", message.channel.sent[-1])

    async def test_answers_mod_list_question_with_direct_mention(self):
        message = FakeMessage(
            content="<@999> what mod's are installed?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("not connected", message.channel.sent[0])

    async def test_ignores_unsupported_message_without_direct_mention(self):
        message = FakeMessage(
            content="hello there",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertFalse(handled)
        self.assertEqual(message.channel.sent, [])

    async def test_supported_status_question_with_missing_guild_mapping(self):
        message = FakeMessage(
            content="<@999> is the server up?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertIn("not connected", message.channel.sent[0])

    async def test_ignores_own_messages(self):
        message = FakeMessage(
            content="<@999> is the server up?",
            author=self.bot,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertFalse(handled)
        self.assertEqual(message.channel.sent, [])

    async def test_direct_command_gets_reason_when_no_reply_generated(self):
        message = FakeMessage(
            content="<@999> is the server up?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[self.bot],
        )

        with patch("twe.discord_bot.service.respond_to_request", return_value=None):
            handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})

        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("Reason:", message.channel.sent[0])

    async def test_slash_command_is_deferred_before_provider_work(self):
        interaction = FakeInteraction()
        safe_mentions = object()

        with patch(
            "twe.discord_bot.service.respond_to_request",
            return_value=BotReply("Genesis is ready.", "server_up"),
        ):
            reply = await handle_interaction(
                interaction,
                "server_status",
                FakeDatabase(),
                self.config,
                {},
                allowed_mentions=safe_mentions,
            )

        self.assertEqual(reply.code, "server_up")
        self.assertEqual(interaction.events[0], ("defer", True, False))
        self.assertEqual(interaction.events[1][0], "followup")
        self.assertIs(interaction.events[1][3], safe_mentions)

    async def test_restart_slash_response_is_ephemeral(self):
        interaction = FakeInteraction()
        with patch(
            "twe.discord_bot.service.respond_to_request",
            return_value=BotReply("Restart is disabled.", "restart_authorized_not_enabled"),
        ):
            await handle_interaction(
                interaction, "server_restart", FakeDatabase(), self.config, {},
            )

        self.assertEqual(interaction.events[0], ("defer", True, True))
        self.assertTrue(interaction.events[1][2])


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.sent = []
        self.last_send_options = {}

    async def send(self, text, **options):
        self.sent.append(text)
        self.last_send_options = options


class FakeMessage:
    def __init__(self, content, author, guild, channel, mentions):
        self.content = content
        self.author = author
        self.guild = guild
        self.channel = channel
        self.mentions = mentions


class FakeInteractionResponse:
    def __init__(self, events):
        self.events = events

    async def defer(self, *, thinking, ephemeral):
        self.events.append(("defer", thinking, ephemeral))


class FakeInteractionFollowup:
    def __init__(self, events):
        self.events = events

    async def send(self, text, *, ephemeral, allowed_mentions=None):
        self.events.append(("followup", text, ephemeral, allowed_mentions))


class FakeInteraction:
    def __init__(self):
        self.guild_id = 222
        self.channel_id = 333
        self.user = FakeUser(444)
        self.events = []
        self.response = FakeInteractionResponse(self.events)
        self.followup = FakeInteractionFollowup(self.events)


class FakeDatabase:
    def connect(self):
        return FakeConnection()


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return FakeCursor()


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, _query, _params=()):
        return None

    def fetchone(self):
        return None


if __name__ == "__main__":
    unittest.main()
