import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import Config
from twe.discord_bot.personality import (
    PERSONALITY_LABELS,
    PERSONALITY_PRESETS,
    SocialResponseRotator,
    classify_social_intent,
    personality_preview,
)
from twe.discord_bot.service import (
    capability_help_reply,
    handle_message,
    handle_personality_interaction,
)


class TrogPersonalityTests(unittest.TestCase):
    def test_approved_presets_have_clear_labels(self):
        self.assertEqual(
            PERSONALITY_PRESETS,
            ("friendly", "direct", "sarcastic", "professional", "enthusiastic"),
        )
        self.assertEqual(
            tuple(PERSONALITY_LABELS[preset] for preset in PERSONALITY_PRESETS),
            ("Friendly", "Direct", "Sarcastic", "Professional", "Enthusiastic"),
        )

    def test_classifies_reviewed_social_questions_without_swallowing_world_questions(self):
        examples = {
            "<@999> are you there?": "presence",
            "@Trog how are you today?": "wellbeing",
            "<@&555> where does your name come from?": "name_origin",
            "@Trog who are you?": "identity",
            "@Trog hello": "greeting",
            "@Trog thank you": "thanks",
            "@Trog good night": "farewell",
            "@Trog good bot": "praise",
        }
        for message, expected in examples.items():
            with self.subTest(message=message):
                self.assertEqual(classify_social_intent(message), expected)
        self.assertIsNone(classify_social_intent("@Trog hey, what are the breeding settings?"))
        self.assertIsNone(classify_social_intent("@Trog tell me whether the World is online"))

    def test_rotates_every_response_before_repeating(self):
        rotator = SocialResponseRotator()
        replies = [rotator.choose("guild", "direct", "presence") for _ in range(5)]
        self.assertEqual(len(set(replies[:4])), 4)
        self.assertEqual(replies[4], replies[0])

    def test_preview_uses_plain_language_label_and_examples(self):
        preview = personality_preview("professional")
        self.assertIn("**Professional**", preview)
        self.assertIn("Presence:", preview)
        self.assertIn("Wellbeing:", preview)
        self.assertIn("Name:", preview)

    @patch("twe.discord_bot.service.personality_for_guild", return_value="friendly")
    @patch("twe.discord_bot.service.authorize")
    @patch("twe.discord_bot.service.resolve_guild")
    def test_capability_help_only_advertises_authorized_actions(
        self, resolve_mock, authorize_mock, _personality_mock,
    ):
        resolve_mock.return_value = SimpleNamespace(game_server_name="Genesis")
        authorize_mock.side_effect = lambda _conn, _guild, _channel, _user, capability: (
            SimpleNamespace(allowed=capability in {
                "instance.status.read",
                "instance.players.count.read",
            })
        )

        reply = capability_help_reply(object(), "222", "333", "111")

        self.assertEqual(reply.code, "server_help")
        self.assertIn("**Genesis**", reply.text)
        self.assertIn("Check whether the World is online and ready", reply.text)
        self.assertIn("Tell you how many players are online", reply.text)
        self.assertNotIn("Tell you who's playing", reply.text)
        self.assertNotIn("Restart the World", reply.text)
        self.assertNotIn("combined overview", reply.text)
        self.assertIn("ask in your own words", reply.text)
        self.assertNotIn("/server", reply.text)
        self.assertNotIn("/trog", reply.text)


class TrogPersonalityInteractionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = Config(database_url="postgresql://unused")
        self.bot = FakeUser(999)
        self.author = FakeUser(111)

    @patch("twe.discord_bot.service.personality_for_guild", return_value="friendly")
    async def test_direct_mention_answers_social_question_without_brain_or_provider(
        self, _personality_mock,
    ):
        message = FakeMessage(
            "<@999> are you there?",
            self.author,
            FakeGuild(222, owner_id=111),
            FakeChannel(333),
            [self.bot],
        )
        rotator = SocialResponseRotator()

        handled = await handle_message(
            message,
            self.bot,
            FakeDatabase(),
            self.config,
            {},
            social_response_rotator=rotator,
        )

        self.assertTrue(handled)
        self.assertEqual(message.channel.sent, ["Sure am. What can I help you with?"])

    @patch("twe.discord_bot.service.update_guild_personality")
    @patch("twe.discord_bot.service.personality_for_guild", return_value="friendly")
    async def test_live_discord_owner_can_change_personality(self, _current_mock, update_mock):
        update_mock.return_value = {
            "id": "installation",
            "community_id": "community",
            "personality_preset": "enthusiastic",
        }
        interaction = FakeInteraction(user_id=111, owner_id=111)

        reply = await handle_personality_interaction(
            interaction,
            "set",
            FakeDatabase(),
            preset="enthusiastic",
        )

        self.assertEqual(reply.code, "trog_personality_updated")
        self.assertIn("**Enthusiastic**", reply.text)
        update_mock.assert_called_once_with(ANY, "222", "enthusiastic", "111")

    @patch("twe.discord_bot.service.update_guild_personality")
    @patch("twe.discord_bot.service.personality_for_guild", return_value="friendly")
    async def test_non_owner_cannot_change_personality(self, _current_mock, update_mock):
        interaction = FakeInteraction(user_id=444, owner_id=111)

        reply = await handle_personality_interaction(
            interaction,
            "set",
            FakeDatabase(),
            preset="sarcastic",
        )

        self.assertEqual(reply.code, "trog_personality_denied")
        self.assertIn("Only the Discord server owner", reply.text)
        update_mock.assert_not_called()

    @patch("twe.discord_bot.service.personality_for_guild", return_value="friendly")
    async def test_any_member_can_preview_without_changing_setting(self, _current_mock):
        interaction = FakeInteraction(user_id=444, owner_id=111)

        reply = await handle_personality_interaction(
            interaction,
            "preview",
            FakeDatabase(),
            preset="sarcastic",
        )

        self.assertEqual(reply.code, "trog_personality_previewed")
        self.assertIn("**Sarcastic**", reply.text)
        self.assertTrue(interaction.events[-1][2])


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class FakeGuild:
    def __init__(self, guild_id, owner_id):
        self.id = guild_id
        self.owner_id = owner_id
        self.me = SimpleNamespace(roles=[])


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id
        self.sent = []

    async def send(self, text, **_options):
        self.sent.append(text)


class FakeMessage:
    def __init__(self, content, author, guild, channel, mentions):
        self.content = content
        self.author = author
        self.guild = guild
        self.channel = channel
        self.mentions = mentions
        self.role_mentions = []


class FakeResponse:
    def __init__(self, events):
        self.events = events

    async def defer(self, *, thinking, ephemeral):
        self.events.append(("defer", thinking, ephemeral))


class FakeFollowup:
    def __init__(self, events):
        self.events = events

    async def send(self, text, *, ephemeral, allowed_mentions=None):
        self.events.append(("followup", text, ephemeral, allowed_mentions))


class FakeInteraction:
    def __init__(self, user_id, owner_id):
        self.guild_id = 222
        self.channel_id = 333
        self.user = FakeUser(user_id)
        self.guild = FakeGuild(222, owner_id)
        self.events = []
        self.response = FakeResponse(self.events)
        self.followup = FakeFollowup(self.events)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeDatabase:
    def connect(self):
        return FakeConnection()


if __name__ == "__main__":
    unittest.main()
