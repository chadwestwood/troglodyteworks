#!/usr/bin/env python3
"""Verify required production secret names without printing their values."""

from __future__ import annotations

import argparse
import os


PROFILES = {
    "web": (
        "TWE_DATABASE_URL",
        "TWE_COOKIE_SECURE",
        "TWE_GOOGLE_CLIENT_ID",
        "TWE_GOOGLE_CLIENT_SECRET",
        "TROG_DISCORD_CLIENT_ID",
        "TROG_DISCORD_CLIENT_SECRET",
        "TROG_DISCORD_BOT_TOKEN",
        "TWE_PROVIDER_SECRET_ACTIVE_KEY_VERSION",
        "TWE_PROVIDER_SECRET_KEYS_JSON",
    ),
    "worker": (
        "TWE_DATABASE_URL",
        "TROG_DISCORD_BOT_TOKEN",
        "TWE_PROVIDER_SECRET_ACTIVE_KEY_VERSION",
        "TWE_PROVIDER_SECRET_KEYS_JSON",
    ),
}


def inventory(profile: str) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for name in PROFILES[profile]:
        if os.environ.get(name, "").strip():
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=sorted(PROFILES))
    args = parser.parse_args()
    present, missing = inventory(args.profile)
    print(f"Secret inventory profile: {args.profile}")
    print(f"Configured names ({len(present)}): {', '.join(present) or 'none'}")
    print(f"Missing names ({len(missing)}): {', '.join(missing) or 'none'}")
    if args.profile == "web" and os.environ.get("TWE_COOKIE_SECURE", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        print("Invalid production setting: TWE_COOKIE_SECURE must be true.")
        return 1
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
