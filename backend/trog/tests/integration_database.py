"""Fail-closed database configuration for PostgreSQL integration tests."""

from __future__ import annotations

import os
from dataclasses import replace
from urllib.parse import unquote, urlparse

from twe.config import load_config


APPLICATION_DATABASE_NAMES = {"postgres", "template0", "template1", "twe"}


def load_integration_config():
    loaded = load_config()
    database_url = os.environ.get("TWE_TEST_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "PostgreSQL integration tests require TWE_TEST_DATABASE_URL; "
            "the application database is never used as a fallback."
        )
    database_name = unquote(urlparse(database_url).path.lstrip("/"))
    if database_name in APPLICATION_DATABASE_NAMES or not database_name.endswith("_test"):
        raise RuntimeError(
            "TWE_TEST_DATABASE_URL must name a dedicated database ending in '_test' "
            "and must not name the application database."
        )
    return replace(loaded, database_url=database_url)
