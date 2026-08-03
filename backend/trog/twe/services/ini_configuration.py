"""Lossless-enough INI parsing for configuration evidence.

Assignments are never replaced by schema defaults and duplicate keys are kept
as separate observations. Sensitive values are identified before persistence.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


_INTEGER = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?$")
_SENSITIVE = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class IniObservation:
    source_section: str | None
    source_key: str
    occurrence_index: int
    line_number: int
    raw_value: str | None
    raw_value_hash: str | None
    typed_value: object | None
    value_type: str | None
    is_sensitive: bool


@dataclass(frozen=True)
class ParsedIni:
    observations: tuple[IniObservation, ...]
    diagnostic_line_hashes: tuple[str, ...]


def _hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _typed(raw: str) -> tuple[object, str]:
    stripped = raw.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True, "boolean"
    if lowered == "false":
        return False, "boolean"
    if _INTEGER.fullmatch(stripped):
        return int(stripped), "integer"
    if _DECIMAL.fullmatch(stripped):
        try:
            value = Decimal(stripped)
        except InvalidOperation:
            return raw, "string"
        if value.is_finite():
            return float(value), "number"
    return raw, "string"


def parse_ini(content: str) -> ParsedIni:
    section = None
    observations = []
    diagnostics = []
    occurrences = defaultdict(int)
    for line_number, line in enumerate(content.lstrip("\ufeff").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith((";", "#")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip() or None
            continue
        if "=" not in line:
            diagnostics.append(_hash(line))
            continue
        key_part, raw_value = line.split("=", 1)
        key = key_part.strip()
        if not key:
            diagnostics.append(_hash(line))
            continue
        occurrence_key = ((section or "").casefold(), key.casefold())
        occurrence_index = occurrences[occurrence_key]
        occurrences[occurrence_key] += 1
        sensitive = bool(_SENSITIVE.search(f"{section or ''}.{key}"))
        typed_value, value_type = (None, None) if sensitive else _typed(raw_value)
        observations.append(
            IniObservation(
                source_section=section,
                source_key=key,
                occurrence_index=occurrence_index,
                line_number=line_number,
                raw_value=None if sensitive else raw_value,
                raw_value_hash=None if sensitive else _hash(raw_value),
                typed_value=typed_value,
                value_type=value_type,
                is_sensitive=sensitive,
            )
        )
    return ParsedIni(tuple(observations), tuple(diagnostics))
