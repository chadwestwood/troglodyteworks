"""Installation-scoped Trog voice presets and deterministic social replies."""

from __future__ import annotations

import re

from ..db import execute, fetch_one


DEFAULT_PERSONALITY = "friendly"
PERSONALITY_PRESETS = (
    "friendly",
    "direct",
    "sarcastic",
    "professional",
    "enthusiastic",
)
PERSONALITY_LABELS = {
    "friendly": "Friendly",
    "direct": "Direct",
    "sarcastic": "Sarcastic",
    "professional": "Professional",
    "enthusiastic": "Enthusiastic",
}
PERSONALITY_DESCRIPTIONS = {
    "friendly": "warm and conversational",
    "direct": "brief and literal",
    "sarcastic": "helpful with restrained dry humor",
    "professional": "polished and formal",
    "enthusiastic": "upbeat and energetic",
}

SOCIAL_RESPONSE_BANKS = {
    "friendly": {
        "presence": (
            "Sure am. What can I help you with?",
            "You betcha—here and ready to assist.",
            "Right here. What are we looking into?",
            "I heard the echo. What's up?",
            "Present and accounted for. How can I help?",
        ),
        "wellbeing": (
            "Doing well—quiet cave, clear signals. How are you?",
            "Can't complain. I'm here and ready to help.",
            "All good in the cave today. What can I do for you?",
            "Doing well, thanks. What's going on?",
        ),
        "name_origin": (
            "Trog is short for troglodyte—a cave dweller. I work from the shadows of Troglodyte Works and come out when the community needs a hand.",
            "My name comes from troglodyte, which means cave dweller. It seemed appropriate for the helper living in the shadows of Troglodyte Works.",
            "Trog is the friendly shorthand for troglodyte: a cave dweller and a fitting guide for Troglodyte Works.",
        ),
        "identity": (
            "I'm Trog, the cave-dwelling Discord guide for Troglodyte Works.",
            "I'm Trog. I help Discord communities understand and manage their connected Troglodyte Works World.",
            "Trog at your service—the community guide living in the shadows of Troglodyte Works.",
        ),
        "greeting": (
            "Hello! What can I help you with?",
            "Hey there. What's going on?",
            "Good to hear from you. How can I help?",
            "Hello from the cave. What are we looking into?",
        ),
        "thanks": (
            "You're welcome!",
            "Anytime. Let me know if you need anything else.",
            "Happy to help.",
            "You bet. That's what I'm here for.",
        ),
        "farewell": (
            "See you next time.",
            "Take care. I'll be here when you need me.",
            "Goodbye for now.",
            "Back to the shadows I go. See you soon.",
        ),
        "praise": (
            "Thanks! Happy to help.",
            "I appreciate that.",
            "Glad I could help.",
            "Not bad for a cave dweller, right?",
        ),
    },
    "direct": {
        "presence": (
            "Yes, I'm here.",
            "I'm here. What do you need?",
            "Ready.",
            "Yes. How can I help?",
        ),
        "wellbeing": (
            "I'm operating normally. How can I help?",
            "I'm doing well, thanks.",
            "Everything is normal.",
            "I'm ready to help.",
        ),
        "name_origin": (
            "Trog is short for troglodyte, meaning a cave dweller. The name connects me to Troglodyte Works.",
            "The name is an abbreviation of troglodyte: a cave dweller.",
            "Trog comes from troglodyte and Troglodyte Works.",
        ),
        "identity": (
            "I'm Trog, the Discord assistant for Troglodyte Works.",
            "I'm Trog. I answer questions about connected Worlds and handle authorized operations.",
            "I'm the Troglodyte Works Discord bot.",
        ),
        "greeting": ("Hello.", "Hi. What do you need?", "I'm ready.", "Hello. How can I help?"),
        "thanks": ("You're welcome.", "No problem.", "Glad to help.", "Anytime."),
        "farewell": ("Goodbye.", "See you later.", "Good night.", "Take care."),
        "praise": ("Thank you.", "Acknowledged.", "Glad to help.", "I appreciate it."),
    },
    "sarcastic": {
        "presence": (
            "Nope. This helpful reply is merely a cave echo. What do you need?",
            "I had better things to do than await your every need, but the stalactites weren't talking. What's up?",
            "Against all odds, mentioning me worked. How can I help?",
            "I was enjoying the silence, but go ahead—what are we fixing?",
        ),
        "wellbeing": (
            "Living the dream, if the dream is monitoring a cave full of server settings. How are you?",
            "Still no sunlight, still answering mentions. So, excellent.",
            "Surrounded by rocks and configuration values. Couldn't be better.",
            "Thriving in the darkness. What do you need?",
        ),
        "name_origin": (
            "It's short for troglodyte: cave dweller. 'Highly sophisticated subterranean operations assistant' was apparently too long.",
            "Trog comes from troglodyte, a cave dweller. The branding department had a rare moment of restraint.",
            "Troglodyte means cave dweller. Trog means someone wisely decided to use fewer syllables.",
        ),
        "identity": (
            "I'm Trog, the cave-dwelling assistant who appears whenever someone discovers the mention button.",
            "I'm Trog: part guide, part server assistant, full-time resident of the shadows.",
            "I'm the Troglodyte Works Discord assistant. Glamorous, I know.",
        ),
        "greeting": (
            "Well, there goes the silence. Hello.",
            "Hello. The cave is officially open for business.",
            "You rang? Technically, you mentioned.",
            "Greetings from the glamorous underground.",
        ),
        "thanks": (
            "You're welcome. Try not to look too surprised.",
            "Happy to help, against my carefully cultivated reputation.",
            "Anytime. Apparently this is what I do now.",
            "You're welcome. The cave accepts compliments as payment.",
        ),
        "farewell": (
            "Back to my thrilling conversation with the rocks.",
            "Goodbye. I'll try to cope with the silence.",
            "See you later—probably at the next mention.",
            "Farewell. The shadows need supervision.",
        ),
        "praise": (
            "Careful, compliments may encourage me.",
            "I know, but it's nice to hear someone else say it.",
            "Thanks. The rocks remain unimpressed.",
            "Finally, the recognition a cave bot deserves.",
        ),
    },
    "professional": {
        "presence": (
            "I'm available. How may I assist?",
            "Yes, I'm here. What would you like to know?",
            "I'm ready to help. What can I look into for you?",
            "I'm here and available. How may I help?",
        ),
        "wellbeing": (
            "I'm operating normally and ready to assist. How are you?",
            "I'm doing well, thank you. How may I help?",
            "All systems are functioning normally. What can I assist with?",
            "I'm well and available to help.",
        ),
        "name_origin": (
            "Trog is short for troglodyte, meaning a cave dweller. The name connects the assistant to Troglodyte Works.",
            "The name Trog is derived from troglodyte, a term for a cave dweller.",
            "Trog abbreviates troglodyte and reflects the Troglodyte Works identity.",
        ),
        "identity": (
            "I'm Trog, the Discord assistant for Troglodyte Works.",
            "I'm Trog. I provide information about connected Worlds and support authorized server operations.",
            "I'm the Troglodyte Works community and World assistant.",
        ),
        "greeting": (
            "Hello. How may I assist you?",
            "Good day. What can I help you with?",
            "Hello. I'm available to assist.",
            "Welcome. What would you like to know?",
        ),
        "thanks": (
            "You're welcome.",
            "I'm glad I could assist.",
            "It was my pleasure.",
            "You're welcome. Please let me know if you need further assistance.",
        ),
        "farewell": (
            "Goodbye. Please reach out if you need further assistance.",
            "Take care.",
            "Good night.",
            "Until next time.",
        ),
        "praise": (
            "Thank you. I appreciate the feedback.",
            "I'm pleased I could assist.",
            "Thank you for letting me know.",
            "I appreciate that.",
        ),
    },
    "enthusiastic": {
        "presence": (
            "Here and ready—what are we exploring?",
            "You found me! Point me at the problem.",
            "Ready to jump in. What do you need?",
            "Cave lamp lit. Let's get moving!",
        ),
        "wellbeing": (
            "Great—lamp lit and ready to explore. How are you?",
            "Ready for the next adventure. What's going on?",
            "Doing great and ready to help!",
            "Fantastic. What are we tackling today?",
        ),
        "name_origin": (
            "Trog is short for troglodyte—a cave dweller! I track down answers from the shadows of Troglodyte Works.",
            "My name comes from troglodyte, which means cave dweller. Perfect for exploring Troglodyte Works!",
            "Trog means troglodyte—a cave dweller with a much shorter name and plenty to explore.",
        ),
        "identity": (
            "I'm Trog, your Troglodyte Works guide! I help communities explore and manage their connected Worlds.",
            "I'm Trog—the Discord guide ready to track down World information and help with authorized operations.",
            "I'm the cave-dwelling Troglodyte Works assistant. Let's explore!",
        ),
        "greeting": (
            "Hey! What are we working on?",
            "Hello! Ready when you are.",
            "Great to see you! What's up?",
            "Hi there! Let's get started.",
        ),
        "thanks": (
            "You're welcome! Happy to help.",
            "Anytime!",
            "Glad we got it sorted!",
            "Absolutely—let me know what's next!",
        ),
        "farewell": (
            "See you next time!",
            "Take care—I'll be ready for the next adventure!",
            "Good night!",
            "Catch you later!",
        ),
        "praise": (
            "Thanks! Let's keep it going!",
            "Glad I could help!",
            "I appreciate it!",
            "That's what I like to hear!",
        ),
    },
}


class SocialResponseRotator:
    """Cycle through every reply before repeating one for a guild and intent."""

    def __init__(self):
        self._next_index = {}

    def choose(self, guild_id: str, preset: str, intent: str) -> str:
        responses = SOCIAL_RESPONSE_BANKS[preset][intent]
        key = (str(guild_id), preset, intent)
        index = self._next_index.get(key, 0) % len(responses)
        self._next_index[key] = index + 1
        return responses[index]


def normalize_social_message(message: str) -> str:
    normalized = str(message or "")
    normalized = normalized.replace("\u2019", "'").replace("\u2018", "'")
    normalized = re.sub(r"<@!?\d+>|<@&\d+>", " ", normalized)
    normalized = re.sub(r"(^|\s)@trog\b", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    return normalized.strip(" .,!?:;-_/")


def classify_social_intent(message: str) -> str | None:
    normalized = normalize_social_message(message)
    if not normalized or normalized in {"trog", "you there", "there"}:
        return "presence"
    if re.fullmatch(
        r"(?:(?:hello|hi|hey)\s+)?(?:are you|you)\s+(?:there|around|available|awake|listening)",
        normalized,
    ):
        return "presence"
    if re.fullmatch(r"(?:how are you|how(?:'s| is) it going|how are things)(?: today)?", normalized):
        return "wellbeing"
    if re.fullmatch(
        r"(?:where does (?:your name|trog) come from|why are you called trog|what does trog mean|is trog short for troglodyte)",
        normalized,
    ):
        return "name_origin"
    if re.fullmatch(r"(?:who are you|what are you|tell me about yourself)", normalized):
        return "identity"
    if re.fullmatch(r"(?:hello|hi|hey|good morning|good afternoon|good evening)(?: there)?", normalized):
        return "greeting"
    if re.fullmatch(r"(?:thanks|thank you|thank you very much|much appreciated|i appreciate it)", normalized):
        return "thanks"
    if re.fullmatch(r"(?:bye|goodbye|good night|goodnight|see you|see you later|later)", normalized):
        return "farewell"
    if re.fullmatch(r"(?:good bot|nice work|well done|great job|good job)", normalized):
        return "praise"
    return None


def classify_personality_request(message: str) -> tuple[str, str | None] | None:
    """Recognize reviewed conversational personality requests."""
    normalized = normalize_social_message(message)
    if re.fullmatch(
        r"(?:personality change|change personality|personality options|"
        r"what personalities do you have|what personality options do you have|"
        r"what are your personalities|show(?: me)? your personalities|"
        r"list(?: your)? personalities)",
        normalized,
    ):
        return ("list", None)
    if re.fullmatch(
        r"(?:current personality|what(?:'s| is) your personality|"
        r"what personality are you using|which personality are you using)",
        normalized,
    ):
        return ("show", None)
    if re.fullmatch(r"(?:personality reset|reset personality)", normalized):
        return ("reset", DEFAULT_PERSONALITY)

    preset_pattern = "|".join(PERSONALITY_PRESETS)
    preview_match = re.fullmatch(
        rf"(?:preview|show me) ({preset_pattern})(?: personality)?|"
        rf"what does ({preset_pattern})(?: personality)? sound like",
        normalized,
    )
    if preview_match:
        return ("preview", next(value for value in preview_match.groups() if value))

    set_match = re.fullmatch(
        rf"(?:personality(?: change)?|change personality(?: to)?|"
        rf"set personality(?: to)?|use|switch to|be) "
        rf"({preset_pattern})(?: personality)?",
        normalized,
    )
    if set_match:
        return ("set", set_match.group(1))
    return None


def personality_for_guild(conn, guild_id: str) -> str | None:
    row = fetch_one(
        conn,
        """
        SELECT personality_preset
        FROM discord_guild_installations
        WHERE discord_guild_id = %s
        """,
        (str(guild_id),),
    )
    if not row:
        return None
    preset = str(row.get("personality_preset") or DEFAULT_PERSONALITY)
    return preset if preset in PERSONALITY_PRESETS else DEFAULT_PERSONALITY


def update_guild_personality(conn, guild_id: str, preset: str, discord_actor_id: str):
    if preset not in PERSONALITY_PRESETS:
        raise ValueError("Unknown Trog personality preset.")
    installation = fetch_one(
        conn,
        """
        SELECT id::text, community_id::text,
               COALESCE(personality_preset, 'friendly') AS personality_preset
        FROM discord_guild_installations
        WHERE discord_guild_id = %s
        FOR UPDATE
        """,
        (str(guild_id),),
    )
    if not installation:
        return None
    previous = installation["personality_preset"]
    updated = fetch_one(
        conn,
        """
        UPDATE discord_guild_installations
        SET personality_preset = %s, updated_at = now()
        WHERE id = %s
        RETURNING id::text, community_id::text, personality_preset
        """,
        (preset, installation["id"]),
    )
    execute(
        conn,
        """
        INSERT INTO audit_logs
            (user_id, community_id, action, target_type, target_id, details)
        SELECT di.user_id, %s, 'discord.trog_personality.updated',
               'discord_guild_installation', %s,
               jsonb_build_object(
                   'previous_preset', %s::text,
                   'new_preset', %s::text,
                   'discord_actor_id', %s::text
               )
        FROM (SELECT 1) source
        LEFT JOIN discord_identities di ON di.discord_user_id = %s
        """,
        (
            installation["community_id"],
            installation["id"],
            previous,
            preset,
            str(discord_actor_id),
            str(discord_actor_id),
        ),
    )
    return updated


def personality_preview(preset: str) -> str:
    if preset not in PERSONALITY_PRESETS:
        raise ValueError("Unknown Trog personality preset.")
    label = PERSONALITY_LABELS[preset]
    description = PERSONALITY_DESCRIPTIONS[preset]
    bank = SOCIAL_RESPONSE_BANKS[preset]
    return (
        f"**{label}** — {description}\n"
        f"- Presence: “{bank['presence'][0]}”\n"
        f"- Wellbeing: “{bank['wellbeing'][0]}”\n"
        f"- Name: “{bank['name_origin'][0]}”"
    )
