"""Deterministic intent and eligibility rules for verified World settings.

Topic retrieval is deliberately token- and taxonomy-based. Relevance scoring
runs only after eligibility and can never admit a setting into a topic response.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


_WORD_PARTS = re.compile(
    r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z]+|[0-9]+"
)
_WORD_RUNS = re.compile(r"[A-Za-z0-9]+")
_DISCORD_REFERENCE = re.compile(r"<(?:@!?|@&|#)\d+>")

SETTING_TOPIC_TAXONOMY = {
    "harvest": frozenset(
        {"harvest", "harvesting", "gather", "gathering", "resource", "resources"}
    ),
    "tame": frozenset({"tame", "taming"}),
    "breed": frozenset(
        {
            "breed",
            "breeding",
            "mating",
            "hatch",
            "incubation",
            "mature",
            "baby",
            "imprint",
            "cuddle",
        }
    ),
    "experience": frozenset({"xp", "experience"}),
    "difficulty": frozenset({"difficulty"}),
    "damage": frozenset({"damage"}),
    "player": frozenset({"player", "players"}),
    "dino": frozenset({"dino", "dinos", "dinosaur", "creature", "creatures"}),
    "structure": frozenset({"structure", "structures", "building"}),
    "food": frozenset({"food", "hunger"}),
    "water": frozenset({"water", "thirst"}),
    "stamina": frozenset({"stamina"}),
    "interface": frozenset({"interface", "ui", "tab", "menu"}),
    "cosmetic": frozenset({"cosmetic", "cosmetics"}),
}

# Exact-name overrides provide a reviewed extension point for settings whose
# names do not carry enough semantic information. Keys are compact identities,
# never provider paths or values.
SETTING_TOPIC_OVERRIDES: dict[str, frozenset[str]] = {}

_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "all",
        "an",
        "and",
        "are",
        "but",
        "change",
        "current",
        "do",
        "does",
        "easy",
        "feels",
        "for",
        "how",
        "i",
        "is",
        "it",
        "make",
        "map",
        "me",
        "multiplier",
        "multipliers",
        "my",
        "not",
        "of",
        "on",
        "rate",
        "rates",
        "recommend",
        "server",
        "setting",
        "settings",
        "should",
        "the",
        "this",
        "to",
        "too",
        "value",
        "values",
        "want",
        "what",
        "which",
        "world",
        "would",
        "you",
    }
)


@dataclass(frozen=True)
class SettingDescriptor:
    identity: str
    tokens: frozenset[str]
    topic_tags: frozenset[str]


@dataclass(frozen=True)
class SettingQueryIntent:
    tokens: frozenset[str]
    topic_tags: frozenset[str]
    qualifier_tokens: frozenset[str]

    @property
    def is_actionable(self) -> bool:
        return bool(self.topic_tags or self.qualifier_tokens)


def semantic_setting_tokens(value) -> frozenset[str]:
    """Split paths and identifiers into exact human-meaningful tokens."""
    tokens = []
    for word_run in _WORD_RUNS.findall(str(value or "")):
        tokens.extend(part.casefold() for part in _WORD_PARTS.findall(word_run))
    return frozenset(token for token in tokens if len(token) > 1)


def setting_identity(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _topic_tags(tokens: frozenset[str]) -> frozenset[str]:
    return frozenset(
        topic
        for topic, aliases in SETTING_TOPIC_TAXONOMY.items()
        if tokens & aliases
    )


def describe_setting(setting_name) -> SettingDescriptor:
    tokens = semantic_setting_tokens(setting_name)
    identity = setting_identity(setting_name)
    topics = set(_topic_tags(tokens))
    topics.update(SETTING_TOPIC_OVERRIDES.get(identity, ()))
    return SettingDescriptor(identity, tokens, frozenset(topics))


def identify_setting_query_intent(request_text) -> SettingQueryIntent:
    # Discord mention/channel/role IDs are routing metadata, never semantic
    # qualifiers for a setting name.
    request_text = _DISCORD_REFERENCE.sub(" ", str(request_text or ""))
    tokens = semantic_setting_tokens(request_text)
    topics = _topic_tags(tokens)
    topic_aliases = frozenset(
        alias
        for topic in topics
        for alias in SETTING_TOPIC_TAXONOMY[topic]
    )
    qualifiers = tokens - topic_aliases - _QUERY_STOP_WORDS
    return SettingQueryIntent(tokens, topics, qualifiers)


def setting_is_eligible(
    intent: SettingQueryIntent,
    descriptor: SettingDescriptor,
) -> bool:
    """Apply the hard semantic gate before any relevance scoring."""
    if not intent.is_actionable:
        return False
    if intent.topic_tags and not intent.topic_tags.issubset(descriptor.topic_tags):
        return False
    if intent.qualifier_tokens and not intent.qualifier_tokens.issubset(
        descriptor.tokens
    ):
        return False
    return True


def setting_match_score(
    intent: SettingQueryIntent,
    descriptor: SettingDescriptor,
) -> int:
    """Rank only settings that already passed ``setting_is_eligible``."""
    return (
        4 * len(intent.topic_tags & descriptor.topic_tags)
        + 3 * len(intent.qualifier_tokens & descriptor.tokens)
        + len(intent.tokens & descriptor.tokens)
    )
