#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database, DatabaseUnavailable, execute, fetch_one
from twe.security import hash_password


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def main():
    config = load_config()
    email = require_env("TWE_INITIAL_USER_EMAIL").strip().lower()
    password = require_env("TWE_INITIAL_USER_PASSWORD")
    display_name = os.environ.get("TWE_INITIAL_USER_DISPLAY_NAME", "Chad")

    db = Database(config.database_url)
    try:
        with db.connect() as conn:
            user = fetch_one(conn, "SELECT id::text FROM users WHERE lower(email) = %s", (email,))
            if not user:
                user = fetch_one(
                    conn,
                    """
                    INSERT INTO users (email, password_hash, display_name)
                    VALUES (%s, %s, %s)
                    RETURNING id::text
                    """,
                    (email, hash_password(password), display_name),
                )
            else:
                execute(
                    conn,
                    """
                    UPDATE users
                    SET display_name = %s,
                        password_hash = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (display_name, hash_password(password), user["id"]),
                )

            community = fetch_one(conn, "SELECT id::text FROM communities WHERE slug = 'cohorts-in-the-wild'")
            if not community:
                community = fetch_one(
                    conn,
                    """
                    INSERT INTO communities (name, slug, description, created_by)
                    VALUES ('Cohorts in the Wild', 'cohorts-in-the-wild', 'A gaming community.', %s)
                    RETURNING id::text
                    """,
                    (user["id"],),
                )

            execute(
                conn,
                """
                INSERT INTO community_memberships (user_id, community_id, role)
                VALUES (%s, %s, 'owner')
                ON CONFLICT (user_id, community_id) DO UPDATE SET role = 'owner'
                """,
                (user["id"], community["id"]),
            )

            server = fetch_one(
                conn,
                "SELECT id::text FROM game_servers WHERE community_id = %s AND slug = 'ark-survival-ascended'",
                (community["id"],),
            )
            if not server:
                server = fetch_one(
                    conn,
                    """
                    INSERT INTO game_servers
                        (community_id, name, slug, game_type, management_adapter, status)
                    VALUES
                        (%s, 'ARK Survival Ascended', 'ark-survival-ascended', 'ARK Survival Ascended', 'local_asa', 'unknown')
                    RETURNING id::text
                    """,
                    (community["id"],),
                )

            execute(
                conn,
                """
                INSERT INTO game_instances
                    (game_server_id, name, slug, instance_type, game_identifier, status, sort_order)
                VALUES
                    (%s, 'Genesis', 'genesis', 'map', 'Genesis_WP', 'unknown', 1)
                ON CONFLICT (game_server_id, slug) DO UPDATE
                SET name = EXCLUDED.name,
                    instance_type = EXCLUDED.instance_type,
                    game_identifier = EXCLUDED.game_identifier,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = now()
                """,
                (server["id"],),
            )

            execute(
                conn,
                """
                INSERT INTO audit_logs (user_id, community_id, action, target_type, target_id)
                VALUES (%s, %s, 'seed.initial_data', 'community', %s)
                """,
                (user["id"], community["id"], community["id"]),
            )
    except (DatabaseUnavailable, Exception) as exc:
        raise SystemExit(f"Seed failed. Check TWE_DATABASE_URL and PostgreSQL access. {exc.__class__.__name__}")

    print("Initial TWE data is present.")


if __name__ == "__main__":
    main()
