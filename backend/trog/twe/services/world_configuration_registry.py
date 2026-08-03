"""Verified configuration revisions scoped to one authorized game instance."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from ..db import execute, fetch_all, fetch_one
from .ini_configuration import parse_ini
from .provider_contracts import (
    ProviderConfigurationArtifact,
    ProviderConfigurationSnapshot,
    ProviderSetting,
    ProviderSettingsSnapshot,
)
from .world_configuration import sanitize_world_settings


PARSER_VERSION = "trog-ini-1"


@dataclass(frozen=True)
class _ArtifactEvidence:
    source_role: str
    source_locator: str
    content_hash: str
    size_bytes: int
    encoding: str | None
    retrieved_at: str
    observations: tuple[dict, ...]
    diagnostics: tuple[str, ...] = ()


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _decode_ini(content: bytes) -> tuple[str, str]:
    try:
        return content.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return content.decode("latin-1"), "latin-1"


def _provider_settings_evidence(snapshot: ProviderSettingsSnapshot) -> _ArtifactEvidence:
    safe = sanitize_world_settings(snapshot.settings)
    serialized = json.dumps(
        [{"path": item.path, "value": item.value} for item in safe],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    observations = tuple(
        {
            "source_section": None,
            "source_key": item.path,
            "occurrence_index": 0,
            "line_number": None,
            "raw_value": item.value,
            "raw_value_hash": _sha256(item.value.encode("utf-8")),
            "typed_value": item.value,
            "value_type": "string",
            "is_sensitive": False,
        }
        for item in safe
    )
    return _ArtifactEvidence(
        source_role="provider_settings",
        source_locator="nitrado:gameservers/settings",
        content_hash=_sha256(serialized),
        size_bytes=len(serialized),
        encoding="utf-8",
        retrieved_at=snapshot.checked_at,
        observations=observations,
    )


def _ini_evidence(artifact: ProviderConfigurationArtifact) -> _ArtifactEvidence:
    content, encoding = _decode_ini(artifact.content)
    parsed = parse_ini(content)
    return _ArtifactEvidence(
        source_role="saved_ini",
        source_locator=artifact.source_locator,
        content_hash=_sha256(artifact.content),
        size_bytes=len(artifact.content),
        encoding=encoding,
        retrieved_at=artifact.retrieved_at,
        observations=tuple(item.__dict__ for item in parsed.observations),
        diagnostics=parsed.diagnostic_line_hashes,
    )


def _snapshot_hash(artifacts: tuple[_ArtifactEvidence, ...]) -> str:
    digest = hashlib.sha256()
    for artifact in sorted(artifacts, key=lambda item: (item.source_role, item.source_locator)):
        digest.update(artifact.source_role.encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifact.source_locator.encode("utf-8"))
        digest.update(b"\0")
        digest.update(artifact.content_hash.encode("ascii"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def store_verified_world_configuration(
    conn,
    *,
    game_instance_id: str,
    provider_context,
    settings_snapshot: ProviderSettingsSnapshot,
    configuration_snapshot: ProviderConfigurationSnapshot,
) -> ProviderSettingsSnapshot:
    """Validate, persist and atomically promote evidence for one instance.

    The provider lineage is taken exclusively from the already-resolved
    ProviderContext. Callers cannot pass a service ID independently.
    """
    if not game_instance_id or provider_context is None:
        raise ValueError("A resolved game instance and provider context are required.")
    ini_artifacts = tuple(_ini_evidence(item) for item in configuration_snapshot.artifacts)
    if not ini_artifacts:
        raise ValueError("No saved INI artifacts were returned; refusing verification.")
    artifacts = (_provider_settings_evidence(settings_snapshot), *ini_artifacts)
    observation_count = sum(len(item.observations) for item in artifacts)
    if observation_count == 0:
        raise ValueError("The provider returned no explicit configuration assignments.")
    snapshot_hash = _snapshot_hash(artifacts)
    existing = fetch_one(
        conn,
        """
        SELECT id::text
        FROM world_configuration_revisions
        WHERE game_instance_id = %s
          AND provider_resource_id = %s
          AND provider_connection_id = %s
          AND snapshot_hash = %s
        """,
        (
            game_instance_id,
            provider_context.resource.id,
            provider_context.connection.id,
            snapshot_hash,
        ),
    )
    revision_id = existing["id"] if existing else str(uuid.uuid4())
    if not existing:
        diagnostics = sum(len(item.diagnostics) for item in artifacts)
        execute(
            conn,
            """
            INSERT INTO world_configuration_revisions (
                id, game_instance_id, provider_resource_id, provider_connection_id,
                provider_key, external_resource_id, observed_at, parser_version,
                snapshot_hash, validation_state, validation_report
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'verified',%s::jsonb)
            """,
            (
                revision_id,
                game_instance_id,
                provider_context.resource.id,
                provider_context.connection.id,
                provider_context.connection.provider_key,
                provider_context.resource.external_resource_id,
                configuration_snapshot.checked_at,
                PARSER_VERSION,
                snapshot_hash,
                json.dumps(
                    {
                        "artifact_count": len(artifacts),
                        "observation_count": observation_count,
                        "diagnostic_count": diagnostics,
                        "contains_saved_ini": True,
                    },
                    separators=(",", ":"),
                ),
            ),
        )
        for artifact in artifacts:
            artifact_id = str(uuid.uuid4())
            execute(
                conn,
                """
                INSERT INTO world_configuration_artifacts (
                    id, revision_id, game_instance_id, source_role, source_locator,
                    content_hash, size_bytes, encoding, retrieved_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    artifact_id,
                    revision_id,
                    game_instance_id,
                    artifact.source_role,
                    artifact.source_locator,
                    artifact.content_hash,
                    artifact.size_bytes,
                    artifact.encoding,
                    artifact.retrieved_at,
                ),
            )
            for observation in artifact.observations:
                execute(
                    conn,
                    """
                    INSERT INTO world_configuration_observations (
                        id, revision_id, game_instance_id, artifact_id, source_role,
                        source_locator, source_section, source_key, occurrence_index,
                        line_number, raw_value, raw_value_hash, typed_value, value_type,
                        parse_state, explicitly_set, is_sensitive
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'parsed',true,%s)
                    """,
                    (
                        str(uuid.uuid4()),
                        revision_id,
                        game_instance_id,
                        artifact_id,
                        artifact.source_role,
                        artifact.source_locator,
                        observation["source_section"],
                        observation["source_key"],
                        observation["occurrence_index"],
                        observation["line_number"],
                        observation["raw_value"],
                        observation["raw_value_hash"],
                        (
                            None
                            if observation["is_sensitive"]
                            else json.dumps(observation["typed_value"])
                        ),
                        observation["value_type"],
                        observation["is_sensitive"],
                    ),
                )
    execute(
        conn,
        """
        INSERT INTO world_configuration_current_revisions
            (game_instance_id, revision_id, promoted_at)
        VALUES (%s,%s,now())
        ON CONFLICT (game_instance_id) DO UPDATE
        SET revision_id = EXCLUDED.revision_id, promoted_at = EXCLUDED.promoted_at
        """,
        (game_instance_id, revision_id),
    )
    return load_verified_world_configuration(conn, game_instance_id)


def load_verified_world_configuration(conn, game_instance_id: str) -> ProviderSettingsSnapshot | None:
    """Load only the promoted verified revision for this exact instance ID."""
    revision = fetch_one(
        conn,
        """
        SELECT r.id::text, GREATEST(r.observed_at, current.promoted_at) AS observed_at
        FROM world_configuration_current_revisions current
        JOIN world_configuration_revisions r
          ON r.id = current.revision_id
         AND r.game_instance_id = current.game_instance_id
        JOIN game_instances gi ON gi.id = current.game_instance_id
        JOIN game_servers gs ON gs.id = gi.game_server_id
        JOIN provider_resources pr ON pr.id = gs.provider_resource_id
        JOIN provider_connections pc ON pc.id = pr.provider_connection_id
        WHERE current.game_instance_id = %s
          AND r.validation_state = 'verified'
          AND r.provider_resource_id = pr.id
          AND r.provider_connection_id = pc.id
          AND r.provider_key = pc.provider_key
          AND r.external_resource_id = pr.external_resource_id
          AND pc.status = 'active'
          AND pr.available = true
          AND current.promoted_at >= now() - interval '15 minutes'
        """,
        (game_instance_id,),
    )
    if not revision:
        return None
    rows = fetch_all(
        conn,
        """
        SELECT source_role, source_locator, source_section, source_key,
               occurrence_index, raw_value
        FROM world_configuration_observations
        WHERE revision_id = %s
          AND game_instance_id = %s
          AND parse_state = 'parsed'
          AND explicitly_set = true
          AND is_sensitive = false
        ORDER BY source_role, source_locator, source_section NULLS FIRST,
                 source_key, occurrence_index
        """,
        (revision["id"], game_instance_id),
    )
    # A duplicated INI key with different values is ambiguous. Preserve it in
    # the audit trail but exclude it from answers so Trog fails closed per key.
    grouped = {}
    for row in rows:
        identity = (
            row["source_role"],
            row["source_locator"],
            row["source_section"] or "",
            row["source_key"].casefold(),
        )
        grouped.setdefault(identity, []).append(row)
    ini_values_by_key = {}
    for row in rows:
        if row["source_role"] != "saved_ini":
            continue
        ini_values_by_key.setdefault(row["source_key"].casefold(), set()).add(
            str(row["raw_value"])
        )
    conflicted_ini_keys = {
        key for key, values in ini_values_by_key.items() if len(values) > 1
    }
    settings = []
    for group in grouped.values():
        values = {str(item["raw_value"]) for item in group}
        if len(values) != 1:
            continue
        row = group[-1]
        if (
            row["source_role"] == "saved_ini"
            and row["source_key"].casefold() in conflicted_ini_keys
        ):
            continue
        if (
            row["source_role"] == "provider_settings"
            and row["source_key"].split(".")[-1].casefold() in conflicted_ini_keys
        ):
            continue
        if row["source_role"] == "saved_ini":
            path = ".".join(
                part
                for part in (
                    "saved",
                    "ini",
                    row["source_locator"],
                    row["source_section"],
                    row["source_key"],
                )
                if part
            )
        else:
            path = f"saved.provider_settings.{row['source_key']}"
        settings.append(ProviderSetting(path=path, value=str(row["raw_value"])))
    checked_at = revision["observed_at"]
    if hasattr(checked_at, "isoformat"):
        checked_at = checked_at.isoformat()
    return ProviderSettingsSnapshot(settings=tuple(settings), checked_at=str(checked_at))
