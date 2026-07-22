from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CurseForgeModLookup:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 8.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def names_for(self, mod_ids: tuple[str, ...]) -> dict[str, str]:
        numeric_ids = [int(mod_id) for mod_id in mod_ids if mod_id.isdigit()]
        if not numeric_ids:
            return {}
        request = Request(
            f"{self._base_url}/v1/mods",
            data=json.dumps({"modIds": numeric_ids, "filterPcOnly": False}).encode(),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Troglodyte-Works/1.0",
                "x-api-key": self._api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if response.status != 200 or len(body) > MAX_RESPONSE_BYTES:
                    return {}
        except (HTTPError, URLError, TimeoutError):
            return {}
        try:
            payload = json.loads(body)
            rows = payload.get("data", [])
            if not isinstance(rows, list):
                return {}
            resolved = {}
            for row in rows:
                if not isinstance(row, dict) or isinstance(row.get("id"), bool):
                    continue
                mod_id = str(row.get("id", "")).strip()
                name = str(row.get("name", "")).strip()
                if mod_id and name:
                    resolved[mod_id] = name[:500]
            return resolved
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}


class AsaModCatalog:
    """A single application-wide ASA mod ID-to-name catalog."""

    def __init__(self, path: str | Path, lookup=None):
        self._path = Path(path)
        self._lookup = lookup
        self._lock = threading.RLock()

    def enrich(self, mods: list[dict[str, str]]) -> list[dict[str, str]]:
        with self._lock:
            names = self._read_names()
            changed = False

            # Provider-supplied names are authoritative and benefit every community.
            for mod in mods:
                mod_id = str(mod.get("id") or "").strip()
                name = str(mod.get("name") or "").strip()
                if mod_id and name and name != f"Mod {mod_id}" and names.get(mod_id) != name:
                    names[mod_id] = name
                    changed = True

            missing = tuple(
                mod_id
                for mod_id in (str(mod.get("id") or "").strip() for mod in mods)
                if mod_id and mod_id not in names
            )
            if missing and self._lookup:
                for mod_id, name in self._lookup.names_for(missing).items():
                    if mod_id in missing and name and names.get(mod_id) != name:
                        names[mod_id] = name
                        changed = True

            if changed:
                self._write_names(names)

            return [
                {"id": str(mod["id"]), "name": names.get(str(mod["id"]), str(mod["name"]))}
                for mod in mods
            ]

    def _read_names(self) -> dict[str, str]:
        try:
            payload = json.loads(self._path.read_text())
            rows = payload.get("mods", [])
            if not isinstance(rows, list):
                return {}
            return {
                str(row["id"]): str(row["name"])
                for row in rows
                if isinstance(row, dict) and row.get("id") and row.get("name")
            }
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}

    def _write_names(self, names: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": "Shared Troglodyte Works ASA mod catalog; refreshed from providers and CurseForge",
            "mods": [
                {"id": mod_id, "name": names[mod_id]}
                for mod_id in sorted(names, key=lambda value: (not value.isdigit(), int(value) if value.isdigit() else value))
            ],
        }
        temporary = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        temporary.replace(self._path)
