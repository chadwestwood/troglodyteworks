#!/usr/bin/env python3
"""Fast, dependency-free security checks for tracked repository content."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_SCAN_BYTES = 2_000_000

SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("Discord bot token", re.compile(r"\b(?:M|N|O)[A-Za-z\d_-]{20,}\.[A-Za-z\d_-]{6}\.[A-Za-z\d_-]{25,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
)

PLACEHOLDERS = (
    "example",
    "placeholder",
    "put_password_here",
    "replace-with",
    "your-",
)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / item.decode() for item in result.stdout.split(b"\0") if item]


def forbidden_environment_file(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith(".env") and name != ".env.example"


def scan_text(path: Path, text: str) -> list[str]:
    findings: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{path.relative_to(ROOT)}:{line}: possible {label}")

    assignment_files = {".env", ".sh", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
    if path.suffix.lower() in assignment_files or path.name == "Dockerfile":
        assignment = re.compile(
            r"(?im)^\s*(?:export\s+)?[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)\s*=\s*([^\s#]+)"
        )
        for match in assignment.finditer(text):
            value = match.group(1).strip("\"'").lower()
            if not value or value.startswith("${") or any(marker in value for marker in PLACEHOLDERS):
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                f"{path.relative_to(ROOT)}:{line}: possible hard-coded secret assignment"
            )
    return findings


def run() -> list[str]:
    findings: list[str] = []
    for path in tracked_files():
        if not path.is_file():
            continue
        if forbidden_environment_file(path):
            findings.append(f"{path.relative_to(ROOT)}: tracked environment file")
            continue
        if path.stat().st_size > MAX_SCAN_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(path, text))
    return sorted(set(findings))


def main() -> int:
    findings = run()
    if findings:
        print("Security checks failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        print(
            "If this is test data, replace it with an unmistakable placeholder instead of allowlisting a secret-like value.",
            file=sys.stderr,
        )
        return 1
    print("Security checks passed: no tracked environment files or known secret patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
