from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MINECRAFT_GAME_ID = 432
MODPACK_CLASS_ID = 4471


class CurseForgeUnavailable(RuntimeError):
    pass


class CurseForgeModpacks:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: float = 8.0):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def search(self, query: str, page_size: int = 12) -> list[dict]:
        params = urlencode({
            "gameId": MINECRAFT_GAME_ID,
            "classId": MODPACK_CLASS_ID,
            "searchFilter": query,
            "sortField": 2,
            "sortOrder": "desc",
            "pageSize": min(max(page_size, 1), 20),
        })
        rows = self._get(f"/v1/mods/search?{params}").get("data", [])
        return [self._clean_mod(row) for row in rows if self._valid_mod(row)]

    def files(self, project_id: int) -> list[dict]:
        params = urlencode({"pageSize": 50})
        rows = self._get(f"/v1/mods/{project_id}/files?{params}").get("data", [])
        cleaned = [self._clean_file(row) for row in rows if self._valid_file(row)]
        return sorted(cleaned, key=lambda row: row["file_date"], reverse=True)[:20]

    def resolve(self, project_id: int, file_id: int) -> tuple[dict, dict]:
        mod = self._get(f"/v1/mods/{project_id}").get("data")
        file_row = self._get(f"/v1/mods/{project_id}/files/{file_id}").get("data")
        if not self._valid_mod(mod) or not self._valid_file(file_row):
            raise CurseForgeUnavailable("The selected CurseForge modpack is unavailable.")
        return self._clean_mod(mod), self._clean_file(file_row)

    def _get(self, path: str) -> dict:
        request = Request(
            f"{self._base_url}{path}",
            headers={
                "Accept": "application/json",
                "User-Agent": "Troglodyte-Works/1.0",
                "x-api-key": self._api_key,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if response.status != 200 or len(body) > MAX_RESPONSE_BYTES:
                    raise CurseForgeUnavailable("CurseForge is temporarily unavailable.")
        except (HTTPError, URLError, TimeoutError) as error:
            raise CurseForgeUnavailable("CurseForge is temporarily unavailable.") from error
        try:
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError
            return payload
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise CurseForgeUnavailable("CurseForge returned an invalid response.") from error

    @staticmethod
    def _valid_mod(row) -> bool:
        return isinstance(row, dict) and isinstance(row.get("id"), int) and bool(row.get("name")) and row.get("isAvailable", True)

    @staticmethod
    def _valid_file(row) -> bool:
        return isinstance(row, dict) and isinstance(row.get("id"), int) and bool(row.get("displayName")) and row.get("isAvailable", True)

    @staticmethod
    def _clean_mod(row: dict) -> dict:
        logo = row.get("logo") if isinstance(row.get("logo"), dict) else {}
        return {
            "id": row["id"],
            "name": str(row["name"])[:200],
            "summary": str(row.get("summary") or "")[:500],
            "slug": str(row.get("slug") or "")[:200],
            "logo_url": str(logo.get("thumbnailUrl") or "")[:1000],
            "download_count": int(row.get("downloadCount") or 0),
        }

    @staticmethod
    def _clean_file(row: dict) -> dict:
        return {
            "id": row["id"],
            "display_name": str(row["displayName"])[:300],
            "file_name": str(row.get("fileName") or "")[:300],
            "file_date": str(row.get("fileDate") or ""),
            "game_versions": [str(value)[:80] for value in (row.get("gameVersions") or [])[:20]],
            "release_type": int(row.get("releaseType") or 0),
        }
