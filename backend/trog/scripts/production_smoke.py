#!/usr/bin/env python3
"""Run non-mutating checks against the public TWE web service."""

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


def fetch(base_url: str, path: str, timeout: float) -> tuple[int, str, bytes]:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "twe-production-smoke/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read(MAX_RESPONSE_BYTES)
    except HTTPError as error:
        with error:
            return error.code, error.headers.get("Content-Type", ""), error.read(MAX_RESPONSE_BYTES)


def run_checks(base_url: str, timeout: float = 10.0) -> list[CheckResult]:
    checks = (
        ("health", "/health", check_health),
        ("homepage", "/", check_html),
        ("sign-in page", "/auth/sign-in.html", check_html),
        ("authentication boundary", "/api/v1/auth/me", check_auth_boundary),
    )
    results = []
    for name, path, validator in checks:
        try:
            status, content_type, body = fetch(base_url, path, timeout)
            passed, detail = validator(status, content_type, body)
        except (URLError, TimeoutError, OSError) as error:
            passed, detail = False, f"request failed ({type(error).__name__})"
        results.append(CheckResult(name=name, passed=passed, detail=detail))
    return results


def check_health(status: int, content_type: str, body: bytes) -> tuple[bool, str]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, f"expected JSON health response, received HTTP {status}"
    passed = status == 200 and payload == {"status": "ok"}
    return passed, "HTTP 200 with status ok" if passed else f"unexpected health response (HTTP {status})"


def check_html(status: int, content_type: str, body: bytes) -> tuple[bool, str]:
    passed = status == 200 and bool(body.strip()) and "text/html" in content_type.lower()
    return passed, "HTTP 200 HTML" if passed else f"expected non-empty HTML (HTTP {status})"


def check_auth_boundary(status: int, content_type: str, body: bytes) -> tuple[bool, str]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False, f"expected JSON authentication response, received HTTP {status}"
    error_code = (payload.get("error") or {}).get("code") if isinstance(payload, dict) else None
    passed = status == 401 and error_code == "UNAUTHENTICATED"
    return passed, "anonymous request rejected" if passed else f"unexpected auth response (HTTP {status})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://troglodyteworks.com")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    results = run_checks(args.base_url, args.timeout)
    if args.json_output:
        print(json.dumps({"checks": [asdict(result) for result in results]}, indent=2))
    else:
        for result in results:
            marker = "PASS" if result.passed else "FAIL"
            print(f"[{marker}] {result.name}: {result.detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
