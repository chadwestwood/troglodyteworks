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
    "craft": frozenset({"craft", "crafting"}),
    "kill": frozenset({"kill", "killed", "killing"}),
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

_ALL_SCOPE_TOKENS = frozenset({"all", "complete", "every", "everything", "full"})


@dataclass(frozen=True)
class SettingClarificationFacet:
    label: str
    required_topics: frozenset[str]
    required_tokens: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SettingClarificationPolicy:
    topic: str
    all_label: str
    facets: tuple[SettingClarificationFacet, ...]


# Clarification choices are reviewed product language, not model output. New
# topics can be added here after their setting groups and member wording are
# understood. At most two matching facets are shown; "all" safely covers the
# remaining verified groups without turning the question into a data dump.
SETTING_CLARIFICATION_POLICIES = (
    SettingClarificationPolicy(
        topic="experience",
        all_label="all XP multipliers",
        facets=(
            SettingClarificationFacet(
                "harvesting XP",
                frozenset({"experience", "harvest"}),
            ),
            SettingClarificationFacet(
                "crafting XP",
                frozenset({"experience", "craft"}),
            ),
            SettingClarificationFacet(
                "killing XP",
                frozenset({"experience", "kill"}),
            ),
        ),
    ),
)

_QUERY_STOP_WORDS = frozenset(
    {
        "a",
        "all",
        "an",
        "and",
        "are",
        "but",
        "change",
        "complete",
        "current",
        "do",
        "does",
        "easy",
        "every",
        "everything",
        "feels",
        "for",
        "full",
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
        "please",
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
    wants_all: bool = False

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
    return SettingQueryIntent(
        tokens,
        topics,
        qualifiers,
        wants_all=bool(tokens & _ALL_SCOPE_TOKENS),
    )


def setting_clarification_prompt(
    intent: SettingQueryIntent,
    descriptors,
) -> str | None:
    """Return one bounded question when verified settings remain ambiguous.

    The policy is deliberately stateless: a member's next message is resolved
    and authorized as a new request. This prevents clarification state from
    leaking between people or channels.
    """
    if intent.wants_all or intent.qualifier_tokens or len(intent.topic_tags) != 1:
        return None

    policy = next(
        (
            candidate
            for candidate in SETTING_CLARIFICATION_POLICIES
            if intent.topic_tags == frozenset({candidate.topic})
        ),
        None,
    )
    if policy is None:
        return None

    eligible_descriptors = tuple(
        descriptor
        for descriptor in descriptors
        if setting_is_eligible(intent, descriptor)
    )
    if not eligible_descriptors:
        return None

    matched_identities = set()
    available_labels = []
    for facet in policy.facets:
        matching = tuple(
            descriptor
            for descriptor in eligible_descriptors
            if facet.required_topics.issubset(descriptor.topic_tags)
            and facet.required_tokens.issubset(descriptor.tokens)
        )
        if not matching:
            continue
        available_labels.append(facet.label)
        matched_identities.update(descriptor.identity for descriptor in matching)

    distinct_groups = len(available_labels)
    if any(
        descriptor.identity not in matched_identities
        for descriptor in eligible_descriptors
    ):
        distinct_groups += 1
    if distinct_groups < 2 or not available_labels:
        return None

    choices = available_labels[:2] + [policy.all_label]
    if len(choices) == 2:
        joined = " or ".join(choices)
    else:
        joined = f"{choices[0]}, {choices[1]}, or {choices[2]}"
    return f"Did you want {joined}?"


def is_setting_clarification_selection(intent: SettingQueryIntent) -> bool:
    """Recognize a short, stateless answer to a reviewed clarification."""
    for policy in SETTING_CLARIFICATION_POLICIES:
        if policy.topic not in intent.topic_tags:
            continue
        if intent.wants_all:
            return True
        if any(
            facet.required_topics.issubset(intent.topic_tags)
            and facet.required_tokens.issubset(intent.tokens)
            for facet in policy.facets
        ):
            return True
    return False


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
