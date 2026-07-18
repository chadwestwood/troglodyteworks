import sys
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.discord_bot.core import (
    DiscordBotConfigurationError,
    GameServerRef,
    classify_intent,
    is_directly_mentioned,
    parse_guild_game_server_map,
    respond_to_message,
    respond_to_request,
    player_count_reply,
    player_list_reply,
    mod_list_reply,
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
from twe.discord_bot.service import handle_message


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
        self.assertEqual(classify_intent("<@123> what mods are installed?"), "mod_list")
        self.assertEqual(classify_intent("<@123> what mod's are installed?"), "mod_list")
        self.assertEqual(classify_intent("<@123> list active mods"), "mod_list")
        self.assertIsNone(classify_intent("<@123> tell me a joke"))

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
        self.assertEqual(reply.code, "unsupported_question")
        self.assertIn("is the server up", reply.text)

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

    @patch("twe.discord_bot.core.authorize")
    def test_authorized_restart_is_recognized_but_not_executed(self, authorize_mock):
        authorize_mock.return_value = AuthorizationDecision(
            True, "authorized", "instance.restart.execute", self._context(),
            DiscordIdentity("111", "user", "membership", "owner"),
        )
        reply = respond_to_request("server_restart", "222", "333", "111", object(), self.config)
        self.assertEqual(reply.code, "restart_authorized_not_enabled")
        self.assertIn("not enabled yet", reply.text)

    @patch("twe.discord_bot.core.authorize")
    def test_unauthorized_restart_is_denied(self, authorize_mock):
        authorize_mock.return_value = AuthorizationDecision(
            False, "capability_not_granted", "instance.restart.execute", self._context(),
            DiscordIdentity("111", "user", "membership", "member"),
        )
        reply = respond_to_request("server_restart", "222", "333", "111", object(), self.config)
        self.assertEqual(reply.code, "restart_denied")

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
        self.assertIn("is the server up", message.channel.sent[0])

    async def test_answers_supported_status_question_even_without_direct_mention(self):
        message = FakeMessage(
            content="is the server up?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("not connected", message.channel.sent[0])

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

    async def test_answers_player_list_question_without_direct_mention(self):
        message = FakeMessage(
            content="is anyone on the server?",
            author=self.author,
            guild=FakeGuild(222),
            channel=FakeChannel(333),
            mentions=[],
        )
        handled = await handle_message(message, self.bot, FakeDatabase(), self.config, {})
        self.assertTrue(handled)
        self.assertEqual(len(message.channel.sent), 1)
        self.assertIn("not connected", message.channel.sent[0])

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

    async def send(self, text):
        self.sent.append(text)


class FakeMessage:
    def __init__(self, content, author, guild, channel, mentions):
        self.content = content
        self.author = author
        self.guild = guild
        self.channel = channel
        self.mentions = mentions


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
