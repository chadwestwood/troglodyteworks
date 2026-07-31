import asyncio
import hashlib
import json
import logging
import re

from ..db import execute


LOGGER = logging.getLogger("twe.knowledge_gaps")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_SECRET = re.compile(
    r"(?i)\b(?:bearer\s+|sk-[A-Za-z0-9_-]*|(?:password|secret|token|api[_ -]?key)\s*[:=]\s*)\S+"
)
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL = re.compile(r"https?://\S+")
_DISCORD_REFERENCE = re.compile(r"<[@#&]!?[0-9]+>")
_LONG_ID = re.compile(r"\b\d{12,}\b")
_PUNCTUATION = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")
_DEDUPE_FILLER = frozenset(
    {
        "a",
        "an",
        "can",
        "could",
        "do",
        "does",
        "how",
        "i",
        "me",
        "my",
        "please",
        "tell",
        "the",
        "to",
        "trog",
        "you",
    }
)


def sanitize_question(question: str) -> str:
    value = str(question or "")[:4000]
    for pattern, replacement in (
        (_SECRET, "[redacted]"),
        (_EMAIL, "[email]"),
        (_IP, "[ip]"),
        (_URL, "[url]"),
        (_DISCORD_REFERENCE, "[discord-reference]"),
        (_LONG_ID, "[id]"),
    ):
        value = pattern.sub(replacement, value)
    return _WHITESPACE.sub(" ", value).strip()[:1000]


def normalize_question(question: str) -> str:
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", question.lower())).strip()


def dedupe_question(question: str) -> str:
    normalized = normalize_question(question)
    meaningful = [word for word in normalized.split() if word not in _DEDUPE_FILLER]
    return " ".join(meaningful) or normalized


def classify_gap(question: str) -> str:
    normalized = normalize_question(question)
    if re.search(r"\b(add|install|remove|delete|restart|change|set|manage|broadcast|create)\b", normalized):
        return "capability"
    if re.search(
        r"\b(setting|settings|recommend|configuration|configure|easy|hard|rate|rates|"
        r"tame|taming|breed|breeding|boss|harvest|harvesting|multiplier)\b",
        normalized,
    ):
        return "playbook"
    return "knowledge"


def failure_category_for_response(
    response_code: str,
    assistant_response: str = "",
    question: str = "",
) -> str | None:
    code = str(response_code or "").lower()
    message = str(assistant_response or "").lower()
    if not code:
        return "unknown"
    if code == "trog_brain_knowledge_gap":
        return classify_gap(question)
    if code == "trog_brain_refusal":
        if "unavailable" in message or "try again" in message:
            return "provider_outage"
        return "topic_boundary"
    if "rate_limit" in code:
        return "rate_limit"
    if any(word in code for word in ("unauthorized", "forbidden", "permission", "denied")):
        return "authorization"
    if code in {"channel_disabled", "read_not_approved"}:
        return "authorization"
    if any(word in code for word in (
        "channel_unmapped", "world_not_connected", "guild_not_connected",
        "instance_unavailable",
    )):
        return "routing"
    if code == "provider_write_unavailable":
        return "capability"
    if any(word in code for word in ("not_configured", "configuration", "credential")):
        return "configuration"
    if code == "mod_reference_required" or any(
        word in code for word in ("invalid", "ambiguous", "clarification", "missing_argument")
    ):
        return "validation"
    if any(word in code for word in (
        "settings_unavailable", "status_unavailable", "players_unavailable",
        "mods_unavailable", "health_unavailable",
    )):
        return "live_data"
    if code == "provider_operation_failed" or any(word in code for word in (
        "provider_unavailable", "curseforge_unavailable", "language_unavailable",
        "brain_unavailable",
    )):
        return "provider_outage"
    if code in {"no_result", "interaction_unavailable", "internal_error"}:
        return "internal_error"
    if any(word in message for word in (
        "could not answer", "could not process", "can’t verify", "can't verify",
        "unavailable right now", "please try again shortly",
    )):
        return "unknown"
    return None


def record_failed_response(
    database,
    question: str,
    *,
    game_type: str | None = None,
    intent: str | None = None,
    response_code: str = "trog_brain_knowledge_gap",
    assistant_response: str = "",
    failure_category: str | None = None,
    source: str = "discord",
    guild_id: str | None = None,
    channel_id: str | None = None,
    author_id: str | None = None,
) -> None:
    sanitized = sanitize_question(question)
    normalized = normalize_question(sanitized)
    if not normalized:
        return
    gap_type = failure_category or failure_category_for_response(
        response_code,
        assistant_response,
        sanitized,
    )
    if not gap_type:
        return
    safe_response = sanitize_question(assistant_response)
    dedupe_key = dedupe_question(sanitized)
    signature_source = "|".join((game_type or "", intent or "", gap_type, dedupe_key))
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
    safe_context = json.dumps({
        key: value
        for key, value in {
            "source": source,
            "guild_id": str(guild_id) if guild_id else None,
            "channel_id": str(channel_id) if channel_id else None,
            "author_id": str(author_id) if author_id else None,
        }.items()
        if value is not None
    })
    try:
        with database.connect() as conn:
            execute(
                conn,
                """
                INSERT INTO knowledge_gaps (
                    signature, sanitized_question, normalized_question, game_type,
                    intent, gap_type, response_code, safe_context, assistant_response
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (signature) DO UPDATE
                SET occurrence_count = knowledge_gaps.occurrence_count + 1,
                    last_seen_at = now(),
                    sanitized_question = EXCLUDED.sanitized_question,
                    response_code = EXCLUDED.response_code,
                    assistant_response = EXCLUDED.assistant_response,
                    safe_context = EXCLUDED.safe_context
                """,
                (
                    signature,
                    sanitized,
                    normalized,
                    game_type,
                    intent,
                    gap_type,
                    response_code,
                    safe_context,
                    safe_response,
                ),
            )
    except Exception:
        LOGGER.exception("Failed-response capture failed without interrupting the Discord reply.")


def schedule_failed_response(database, question: str, **metadata) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(record_failed_response, database, question, **metadata)
    )

    def consume_result(completed):
        try:
            completed.result()
        except Exception:
            LOGGER.exception("Unexpected failed-response background task failure.")

    task.add_done_callback(consume_result)


def record_knowledge_gap(database, question: str, **metadata) -> None:
    record_failed_response(database, question, **metadata)


def schedule_knowledge_gap(database, question: str, **metadata) -> None:
    schedule_failed_response(database, question, **metadata)
