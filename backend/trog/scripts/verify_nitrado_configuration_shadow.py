#!/usr/bin/env python3
"""Read-only production shadow check for one bound Nitrado World.

The script accepts a TWE game instance UUID, never a Nitrado service ID. It
prints only artifact metadata, counts, and explicitly requested non-sensitive
setting values. It performs no database or provider writes.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database, fetch_one
from twe.services.ini_configuration import parse_ini
from twe.services.provider_resolution import (
    read_game_server_configuration,
    read_game_server_settings,
    resolve_game_server_provider,
)
from twe.services.world_configuration import sanitize_world_settings


_SENSITIVE_SETTING_NAME = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|credential)",
    re.IGNORECASE,
)


def _sha256(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def build_shadow_report(settings_snapshot, configuration_snapshot, expected):
    artifacts = []
    values_by_key = {}
    explicit_count = 0
    sensitive_count = 0
    diagnostic_count = 0
    for artifact in configuration_snapshot.artifacts:
        parsed = parse_ini(_decode(artifact.content))
        explicit_count += len(parsed.observations)
        sensitive_count += sum(item.is_sensitive for item in parsed.observations)
        diagnostic_count += len(parsed.diagnostic_line_hashes)
        artifacts.append(
            {
                "name": posixpath.basename(artifact.source_locator),
                "content_hash": _sha256(artifact.content),
                "size_bytes": len(artifact.content),
                "explicit_assignment_count": len(parsed.observations),
                "diagnostic_count": len(parsed.diagnostic_line_hashes),
            }
        )
        for observation in parsed.observations:
            if observation.is_sensitive or observation.raw_value is None:
                continue
            values_by_key.setdefault(observation.source_key.casefold(), set()).add(
                observation.raw_value.strip()
            )

    comparisons = {}
    for key, expected_value in expected.items():
        values = sorted(values_by_key.get(key.casefold(), set()))
        if not values:
            comparisons[key] = {
                "state": "missing",
                "value": None,
                "expected": str(expected_value),
                "matches": False,
            }
        elif len(values) > 1:
            comparisons[key] = {
                "state": "conflicted",
                "value": None,
                "expected": str(expected_value),
                "matches": False,
            }
        else:
            comparisons[key] = {
                "state": "explicit",
                "value": values[0],
                "expected": str(expected_value),
                "matches": values[0] == str(expected_value),
            }

    safe_provider_settings = sanitize_world_settings(settings_snapshot.settings)
    return {
        "ok": bool(comparisons) and all(
            item["matches"] for item in comparisons.values()
        ),
        "mode": "read_only_shadow",
        "checked_at": configuration_snapshot.checked_at,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "explicit_assignment_count": explicit_count,
        "redacted_sensitive_assignment_count": sensitive_count,
        "diagnostic_count": diagnostic_count,
        "provider_summary_setting_count": len(safe_provider_settings),
        "comparisons": comparisons,
    }


def _expected_settings():
    raw = os.environ.get("TWE_SHADOW_EXPECTED_SETTINGS_JSON", "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("TWE_SHADOW_EXPECTED_SETTINGS_JSON must be valid JSON.") from None
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("At least one expected setting is required.")
    expected = {}
    for key, value in parsed.items():
        if (
            not isinstance(key, str)
            or not key.strip()
            or any(character in key for character in ("\r", "\n", "="))
            or _SENSITIVE_SETTING_NAME.search(key)
            or isinstance(value, (dict, list, bool))
            or value is None
        ):
            raise ValueError(
                "Expected settings must be non-sensitive scalar name/value pairs."
            )
        expected[key.strip()] = str(value).strip()
    return expected


def main():
    stage = "validate_input"
    instance_id = os.environ.get("TWE_SHADOW_GAME_INSTANCE_ID", "").strip()
    try:
        instance_id = str(uuid.UUID(instance_id))
        expected = _expected_settings()
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2

    stage = "load_runtime"
    config = load_config()
    database = Database(config.database_url)
    try:
        stage = "resolve_instance_binding"
        with database.connect() as conn:
            instance = fetch_one(
                conn,
                """
                SELECT gi.id::text, gi.game_server_id::text
                FROM game_instances gi
                JOIN game_servers gs ON gs.id = gi.game_server_id
                WHERE gi.id = %s
                  AND gi.status <> 'failed'
                  AND gs.provider_resource_id IS NOT NULL
                """,
                (instance_id,),
            )
            if not instance:
                raise LookupError("The instance has no active bound provider resource.")
            resolution = resolve_game_server_provider(
                conn,
                instance["game_server_id"],
                correlation_id=str(uuid.uuid4()),
            )
        if not resolution or resolution.mode != "provider" or not resolution.context:
            raise LookupError("The instance did not resolve to a provider context.")
        if resolution.context.connection.provider_key != "nitrado":
            raise LookupError("The bound provider is not Nitrado.")

        stage = "read_provider_settings"
        settings_snapshot = read_game_server_settings(resolution, config)
        stage = "read_saved_ini_files"
        configuration_snapshot = read_game_server_configuration(resolution, config)
        stage = "compare_saved_ini_evidence"
        report = build_shadow_report(
            settings_snapshot,
            configuration_snapshot,
            expected,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "mode": "read_only_shadow",
                    "stage": stage,
                    "error_type": type(exc).__name__,
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
