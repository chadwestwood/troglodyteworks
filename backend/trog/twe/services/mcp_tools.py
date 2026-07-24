import json
from datetime import datetime, timezone

from ..authorization import can_request_capability, instance_access
from ..db import execute, fetch_all
from ..serializers import iso
from .provider_resolution import (
    read_game_server_health,
    read_game_server_mods,
    read_game_server_players,
    resolve_game_server_provider,
)


class McpToolError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class McpReadTools:
    def __init__(self, database, config):
        self.database = database
        self.config = config

    def list_instances(self, identity: dict) -> dict:
        with self.database.connect() as conn:
            rows = fetch_all(
                conn,
                """
                SELECT c.id::text AS community_id, c.name AS community_name,
                       gs.id::text AS game_server_id, gs.name AS game_server_name,
                       gs.game_type, gi.id::text AS instance_id,
                       gi.name AS instance_name, gi.slug AS instance_slug,
                       gi.game_identifier, gi.status, cm.role
                FROM community_memberships cm
                JOIN communities c ON c.id = cm.community_id
                JOIN game_servers gs ON gs.community_id = c.id
                JOIN game_instances gi ON gi.game_server_id = gs.id
                WHERE cm.user_id = %s
                ORDER BY c.name, gs.name, gi.sort_order, gi.name
                """,
                (identity["user_id"],),
            )
            self._audit(
                conn,
                identity,
                "twe_list_instances",
                "completed",
                details={"result_count": len(rows)},
            )
        return {
            "instances": [
                {
                    "community": {"id": row["community_id"], "name": row["community_name"]},
                    "game_server": {
                        "id": row["game_server_id"],
                        "name": row["game_server_name"],
                        "game_type": row["game_type"],
                    },
                    "instance": {
                        "id": row["instance_id"],
                        "name": row["instance_name"],
                        "slug": row["instance_slug"],
                        "game_identifier": row["game_identifier"],
                        "recorded_status": row["status"],
                    },
                    "membership_role": row["role"],
                }
                for row in rows
            ]
        }

    def get_server_status(self, identity: dict, instance_id: str) -> dict:
        access, resolution = self._authorize(identity, instance_id, "instance.status.read", "twe_get_server_status")
        try:
            health = read_game_server_health(resolution, self.config)
            result = health or {
                "overall_status": "unknown",
                "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "checks": [],
            }
            self._record_result(identity, access, instance_id, "twe_get_server_status", "completed")
            return {
                "context": self._context(access),
                "status": result,
            }
        except Exception:
            self._record_result(identity, access, instance_id, "twe_get_server_status", "failed")
            raise McpToolError("PROVIDER_UNAVAILABLE", "The hosting provider could not return server status.") from None

    def get_active_players(self, identity: dict, instance_id: str) -> dict:
        access, resolution = self._authorize(
            identity,
            instance_id,
            "instance.players.count.read",
            "twe_get_active_players",
        )
        with self.database.connect() as conn:
            can_read_names = can_request_capability(access, "instance.players.names.read", conn)
        try:
            players = read_game_server_players(resolution, self.config)
            names = list(players.get("players") or [])
            count = int(players.get("count", len(names)))
            result = {"count": count, "names_included": can_read_names}
            if can_read_names:
                result["players"] = names
            self._record_result(
                identity,
                access,
                instance_id,
                "twe_get_active_players",
                "completed",
                {"count": count, "names_included": can_read_names},
            )
            return {"context": self._context(access), "active_players": result}
        except Exception:
            self._record_result(identity, access, instance_id, "twe_get_active_players", "failed")
            raise McpToolError("PROVIDER_UNAVAILABLE", "The hosting provider could not return active players.") from None

    def get_installed_mods(self, identity: dict, instance_id: str) -> dict:
        access, resolution = self._authorize(
            identity,
            instance_id,
            "instance.mods.names.read",
            "twe_get_installed_mods",
        )
        try:
            mods = read_game_server_mods(resolution, self.config)
            self._record_result(
                identity,
                access,
                instance_id,
                "twe_get_installed_mods",
                "completed",
                {"result_count": len(mods)},
            )
            return {"context": self._context(access), "mods": mods}
        except Exception:
            self._record_result(identity, access, instance_id, "twe_get_installed_mods", "failed")
            raise McpToolError("PROVIDER_UNAVAILABLE", "The hosting provider could not return installed mods.") from None

    def get_operation_history(self, identity: dict, instance_id: str, limit: int = 20) -> dict:
        limit = max(1, min(int(limit), 50))
        access = self._access(identity, instance_id, "twe_get_operation_history")
        with self.database.connect() as conn:
            rows = fetch_all(
                conn,
                """
                SELECT so.id::text, so.capability, so.status, so.current_stage,
                       so.requested_at, so.started_at, so.completed_at,
                       so.result_message, users.display_name AS requested_by
                FROM server_operations so
                JOIN users ON users.id = so.requested_by
                WHERE so.game_instance_id = %s
                ORDER BY so.requested_at DESC
                LIMIT %s
                """,
                (instance_id, limit),
            )
            self._audit(
                conn,
                identity,
                "twe_get_operation_history",
                "completed",
                access=access,
                instance_id=instance_id,
                details={"result_count": len(rows), "limit": limit},
            )
        return {
            "context": self._context(access),
            "operations": [
                {
                    "id": row["id"],
                    "capability": row["capability"],
                    "status": row["status"],
                    "current_stage": row["current_stage"],
                    "requested_at": iso(row["requested_at"]),
                    "started_at": iso(row["started_at"]),
                    "completed_at": iso(row["completed_at"]),
                    "result_message": row["result_message"],
                    "requested_by": row["requested_by"],
                }
                for row in rows
            ],
        }

    def _authorize(self, identity, instance_id, capability, tool_name):
        access = self._access(identity, instance_id, tool_name)
        with self.database.connect() as conn:
            if not can_request_capability(access, capability, conn):
                self._audit(
                    conn,
                    identity,
                    tool_name,
                    "denied",
                    access=access,
                    instance_id=instance_id,
                    details={"required_capability": capability},
                )
                raise McpToolError("FORBIDDEN", "This TWE user does not have the required instance capability.")
            resolution = resolve_game_server_provider(conn, access["game_server_id"])
        if not resolution:
            raise McpToolError("PROVIDER_UNAVAILABLE", "The instance does not have a readable hosting provider.")
        return access, resolution

    def _access(self, identity, instance_id, tool_name):
        with self.database.connect() as conn:
            access = instance_access(conn, identity["user_id"], instance_id)
            if not access:
                self._audit(
                    conn,
                    identity,
                    tool_name,
                    "denied",
                    instance_id=None,
                    details={"reason": "instance_not_accessible"},
                )
                # Deliberately hide whether another tenant owns the supplied ID.
                raise McpToolError("NOT_FOUND", "The instance was not found.")
        return access

    def _record_result(self, identity, access, instance_id, tool_name, outcome, details=None):
        with self.database.connect() as conn:
            self._audit(
                conn,
                identity,
                tool_name,
                outcome,
                access=access,
                instance_id=instance_id,
                details=details,
            )

    @staticmethod
    def _audit(conn, identity, tool_name, outcome, access=None, instance_id=None, details=None):
        audit_details = {"tool": tool_name, "outcome": outcome, "transport": "mcp"}
        audit_details.update(details or {})
        execute(
            conn,
            """
            INSERT INTO audit_logs
                (user_id, community_id, action, target_type, target_id, details)
            VALUES (%s, %s, 'mcp.tool.called', %s, %s, %s::jsonb)
            """,
            (
                identity["user_id"],
                access["community_id"] if access else None,
                "game_instance" if instance_id else "mcp_server",
                instance_id,
                json.dumps(audit_details),
            ),
        )

    @staticmethod
    def _context(access):
        return {
            "community": {"id": access["community_id"], "name": access["community_name"]},
            "game_server": {"id": access["game_server_id"], "name": access["game_server_name"]},
            "instance": {
                "id": access["instance_id"],
                "name": access["instance_name"],
                "slug": access["instance_slug"],
            },
        }

