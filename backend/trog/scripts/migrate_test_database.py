#!/usr/bin/env python3
"""Apply repository migrations to the guarded integration-test database."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import migrate
from tests.integration_database import load_integration_config


def main() -> int:
    config = load_integration_config()
    os.environ["TWE_DATABASE_URL"] = config.database_url
    migrate.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
