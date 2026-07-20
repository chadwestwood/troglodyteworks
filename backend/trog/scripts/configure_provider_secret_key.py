#!/usr/bin/env python3
"""Configure a database-external AES-256 provider-secret key without printing it."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import secrets
import tempfile
from pathlib import Path


KEY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
ACTIVE_VERSION_NAME = "TWE_PROVIDER_SECRET_ACTIVE_KEY_VERSION"
KEYRING_NAME = "TWE_PROVIDER_SECRET_KEYS_JSON"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default="v1",
        help="Key version identifier (letters, digits, dot, underscore, or hyphen).",
    )
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


def update_lines(lines: list[str], replacements: dict[str, str]) -> list[str]:
    output: list[str] = []
    remaining = dict(replacements)
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in remaining and not line.lstrip().startswith("#"):
            output.append(f"{name}={remaining.pop(name)}")
        else:
            output.append(line)
    if remaining and output and output[-1]:
        output.append("")
    output.extend(f"{name}={value}" for name, value in remaining.items())
    return output


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
    if not KEY_VERSION_PATTERN.fullmatch(args.version):
        raise SystemExit("Invalid key version format.")

    lines, values = read_env(ENV_PATH)
    try:
        keyring = json.loads(values.get(KEYRING_NAME, "{}"))
    except json.JSONDecodeError as exc:
        raise SystemExit("Existing provider-secret keyring JSON is invalid.") from exc
    if not isinstance(keyring, dict):
        raise SystemExit("Existing provider-secret keyring must be a JSON object.")
    if args.version in keyring:
        raise SystemExit("That key version already exists; choose a new version.")

    keyring[args.version] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    replacements = {
        ACTIVE_VERSION_NAME: args.version,
        KEYRING_NAME: json.dumps(keyring, separators=(",", ":")),
    }
    atomic_write(ENV_PATH, "\n".join(update_lines(lines, replacements)) + "\n")
    print(f"Configured provider-secret active version {args.version!r} with {len(keyring)} keyring entry/entries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
