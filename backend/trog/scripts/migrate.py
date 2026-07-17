#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from twe.config import load_config
from twe.db import Database, DatabaseUnavailable


def main():
    migration_dir = ROOT / "migrations"
    config = load_config()
    db = Database(config.database_url)
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version text PRIMARY KEY,
                        applied_at timestamptz NOT NULL DEFAULT now()
                    )
                    """
                )
                for path in sorted(migration_dir.glob("*.sql")):
                    version = path.stem
                    cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                    if cur.fetchone():
                        print(f"skip {version}")
                        continue
                    cur.execute(path.read_text())
                    cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                    print(f"apply {version}")
    except (DatabaseUnavailable, Exception) as exc:
        raise SystemExit(f"Migration failed. Check TWE_DATABASE_URL and PostgreSQL access. {exc.__class__.__name__}")


if __name__ == "__main__":
    main()
