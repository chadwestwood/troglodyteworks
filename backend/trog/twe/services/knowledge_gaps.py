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


def record_knowledge_gap(
    database,
    question: str,
    *,
    game_type: str | None = None,
    intent: str | None = None,
    response_code: str = "trog_brain_knowledge_gap",
) -> None:
    sanitized = sanitize_question(question)
    normalized = normalize_question(sanitized)
    if not normalized:
        return
    gap_type = classify_gap(normalized)
    dedupe_key = dedupe_question(sanitized)
    signature_source = "|".join((game_type or "", intent or "", gap_type, dedupe_key))
    signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
    safe_context = json.dumps({"source": "discord"})
    try:
        with database.connect() as conn:
            execute(
                conn,
                """
                INSERT INTO knowledge_gaps (
                    signature, sanitized_question, normalized_question, game_type,
                    intent, gap_type, response_code, safe_context
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (signature) DO UPDATE
                SET occurrence_count = knowledge_gaps.occurrence_count + 1,
                    last_seen_at = now(),
                    sanitized_question = EXCLUDED.sanitized_question,
                    response_code = EXCLUDED.response_code
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
                ),
            )
    except Exception:
        LOGGER.exception("Knowledge-gap capture failed without interrupting the Discord reply.")


def schedule_knowledge_gap(database, question: str, **metadata) -> None:
    task = asyncio.create_task(
        asyncio.to_thread(record_knowledge_gap, database, question, **metadata)
    )

    def consume_result(completed):
        try:
            completed.result()
        except Exception:
            LOGGER.exception("Unexpected knowledge-gap background task failure.")

    task.add_done_callback(consume_result)
