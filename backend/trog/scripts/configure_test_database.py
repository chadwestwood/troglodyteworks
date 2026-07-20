#!/usr/bin/env python3
"""Configure a dedicated test database URL without printing credentials."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
TEST_URL_NAME = "TWE_TEST_DATABASE_URL"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="twe_test")
    return parser.parse_args()


def read_env(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text().splitlines() if path.exists() else []
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        values[name.strip()] = value.strip().strip("'\"")
    return lines, values


def replace_setting(lines: list[str], name: str, value: str) -> list[str]:
    output: list[str] = []
    replaced = False
    for line in lines:
        line_name = line.split("=", 1)[0].strip() if "=" in line else ""
        if line_name == name and not line.lstrip().startswith("#"):
            if not replaced:
                output.append(f"{name}={value}")
                replaced = True
        else:
            output.append(line)
    if not replaced:
        if output and output[-1]:
            output.append("")
        output.append(f"{name}={value}")
    return output


def atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        path.chmod(0o600)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    args = parse_args()
    if args.database != "twe_test":
        raise SystemExit("The supported isolated database name is 'twe_test'.")
    lines, values = read_env(ENV_PATH)
    application_url = values.get("TWE_DATABASE_URL", "postgresql://twe_app@localhost:5432/twe")
    parsed = urlparse(application_url)
    application_database = unquote(parsed.path.lstrip("/"))
    if application_database == args.database:
        raise SystemExit("Application and test database names must differ.")
    test_url = urlunparse(parsed._replace(path=f"/{args.database}"))
    atomic_write(ENV_PATH, "\n".join(replace_setting(lines, TEST_URL_NAME, test_url)) + "\n")
    print(f"Configured isolated test database name {args.database!r}; credentials were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
