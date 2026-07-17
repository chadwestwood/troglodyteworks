#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database, execute, fetch_all, fetch_one


class GenesisBackfillError(RuntimeError):
    pass


def backfill_genesis_provider(conn) -> dict[str, str | bool]:
    matches = fetch_all(
        conn,
        """
        SELECT c.id::text AS community_id,
               gs.id::text AS game_server_id,
               gs.provider_resource_id::text AS current_provider_resource_id,
               gi.id::text AS game_instance_id
        FROM communities c
        JOIN game_servers gs ON gs.community_id = c.id
        JOIN game_instances gi ON gi.game_server_id = gs.id
        WHERE c.slug = 'cohorts-in-the-wild'
          AND lower(replace(gs.game_type, ':', '')) = 'ark survival ascended'
          AND (
              lower(gi.name) = 'genesis'
              OR lower(gi.slug) = 'genesis'
              OR gi.game_identifier = 'Genesis_WP'
          )
        FOR UPDATE OF c, gs, gi
        """,
    )
    if len(matches) != 1:
        reason = "missing" if not matches else "ambiguous"
        raise GenesisBackfillError(
            "Genesis provider backfill stopped: expected exactly one Cohorts in the Wild -> "
            f"ARK Survival Ascended -> Genesis topology, found {len(matches)} ({reason}). "
            "Resolve the topology and rerun this command; no provider association was changed."
        )

    topology = matches[0]
    connection = fetch_one(
        conn,
        """
        INSERT INTO provider_connections
            (community_id, provider_key, display_name, auth_strategy, external_account_id,
             status, connected_at, last_verified_at)
        VALUES (%s, 'self_hosted', 'Cohorts self-hosted infrastructure', 'configuration',
                'cohorts-local-asa', 'active', now(), now())
        ON CONFLICT (community_id, provider_key, external_account_id)
        DO UPDATE SET updated_at = provider_connections.updated_at
        RETURNING id::text
        """,
        (topology["community_id"],),
    )
    resource = fetch_one(
        conn,
        """
        INSERT INTO provider_resources
            (provider_connection_id, resource_type, external_resource_id, display_name,
             provider_game_key, normalized_status, provider_status, metadata, selected_at)
        VALUES (%s, 'game_server_service', 'local-asa-genesis', 'Cohorts Genesis host',
                'ark_survival_ascended', 'unknown', 'unknown', '{}'::jsonb, now())
        ON CONFLICT (provider_connection_id, resource_type, external_resource_id)
        DO UPDATE SET updated_at = provider_resources.updated_at
        RETURNING id::text
        """,
        (connection["id"],),
    )

    current_resource_id = topology["current_provider_resource_id"]
    if current_resource_id and current_resource_id != resource["id"]:
        raise GenesisBackfillError(
            "Genesis provider backfill stopped: the existing ARK Game Server is already bound "
            "to a different Provider Resource. Review that binding; no association was changed."
        )

    execute(
        conn,
        """
        UPDATE game_servers
        SET provider_resource_id = %s,
            game_key = COALESCE(game_key, 'ark_survival_ascended'),
            updated_at = CASE
                WHEN provider_resource_id IS DISTINCT FROM %s OR game_key IS NULL THEN now()
                ELSE updated_at
            END
        WHERE id = %s
        """,
        (resource["id"], resource["id"], topology["game_server_id"]),
    )
    execute(
        conn,
        """
        INSERT INTO audit_logs (community_id, action, target_type, target_id, details)
        SELECT %s,
               'provider.foundation.genesis_backfilled',
               'provider_resource',
               %s,
               jsonb_build_object(
                   'provider_key', 'self_hosted',
                   'game_server_id', %s::text,
                   'game_instance_id', %s::text
               )
        WHERE NOT EXISTS (
            SELECT 1
            FROM audit_logs
            WHERE action = 'provider.foundation.genesis_backfilled'
              AND target_type = 'provider_resource'
              AND target_id = %s
        )
        """,
        (
            topology["community_id"],
            resource["id"],
            topology["game_server_id"],
            topology["game_instance_id"],
            resource["id"],
        ),
    )
    return {
        "community_id": topology["community_id"],
        "game_server_id": topology["game_server_id"],
        "game_instance_id": topology["game_instance_id"],
        "provider_connection_id": connection["id"],
        "provider_resource_id": resource["id"],
        "already_bound": current_resource_id == resource["id"],
    }


def main():
    config = load_config()
    with Database(config.database_url).connect() as conn:
        try:
            result = backfill_genesis_provider(conn)
        except GenesisBackfillError as exc:
            conn.rollback()
            raise SystemExit(str(exc)) from exc
    state = "already present" if result["already_bound"] else "created"
    print(
        "Genesis self-hosted provider association "
        f"{state}: community={result['community_id']} game_server={result['game_server_id']} "
        f"instance={result['game_instance_id']} connection={result['provider_connection_id']} "
        f"resource={result['provider_resource_id']}"
    )


if __name__ == "__main__":
    main()
