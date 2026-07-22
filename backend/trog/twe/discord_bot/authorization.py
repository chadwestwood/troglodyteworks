from dataclasses import dataclass

from ..authorization import can_request_capability
from ..db import fetch_all, fetch_one


PUBLIC_CAPABILITIES = frozenset(
    {
        "instance.status.read",
        "instance.players.count.read",
        "instance.players.names.read",
        "instance.mods.names.read",
    }
)
ADMINISTRATIVE_CAPABILITIES = frozenset({"instance.restart.execute"})


@dataclass(frozen=True)
class DiscordContext:
    installation_id: str
    guild_id: str
    community_id: str
    game_server_id: str
    game_server_name: str
    game_server_slug: str
    management_adapter: str
    instance_access_grant_id: str | None = None
    instance_id: str | None = None
    instance_name: str | None = None
    provider_community_name: str | None = None
    channel_scope: str = "all"
    allowed_channel_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscordIdentity:
    discord_user_id: str
    user_id: str | None
    membership_id: str | None
    role: str | None


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    capability: str
    context: DiscordContext | None
    identity: DiscordIdentity | None = None


def resolve_guild(conn, discord_guild_id: str, channel_id: str | None = None) -> DiscordContext | None:
    grant_context = resolve_instance_access_grant(conn, discord_guild_id, channel_id)
    if grant_context:
        return grant_context
    if has_instance_access_grant(conn, discord_guild_id):
        return None
    row = fetch_one(
        conn,
        """
        SELECT dgi.id::text AS installation_id,
               dgi.discord_guild_id,
               dgi.community_id::text,
               gs.id::text AS game_server_id,
               gs.name AS game_server_name,
               gs.slug AS game_server_slug,
               gs.management_adapter
        FROM discord_guild_installations dgi
        JOIN game_servers gs ON gs.id = dgi.game_server_id
        WHERE dgi.discord_guild_id = %s
          AND gs.community_id = dgi.community_id
        """,
        (str(discord_guild_id),),
    )
    if not row:
        return None
    return DiscordContext(
        installation_id=row["installation_id"], guild_id=row["discord_guild_id"],
        community_id=row["community_id"], game_server_id=row["game_server_id"],
        game_server_name=row["game_server_name"], game_server_slug=row["game_server_slug"],
        management_adapter=row["management_adapter"],
    )


def has_instance_access_grant(conn, discord_guild_id: str) -> bool:
    if not instance_access_tables_available(conn):
        return False
    try:
        row = fetch_one(
            conn,
            """
            SELECT diag.id::text
            FROM discord_instance_access_grants diag
            JOIN discord_guild_installations dgi ON dgi.id = diag.discord_guild_installation_id
            WHERE dgi.discord_guild_id = %s
            LIMIT 1
            """,
            (str(discord_guild_id),),
        )
    except Exception:
        return False
    return bool(row)


def resolve_instance_access_grant(conn, discord_guild_id: str, channel_id: str | None = None) -> DiscordContext | None:
    if not instance_access_tables_available(conn):
        return None
    try:
        rows = fetch_all(
            conn,
            """
            SELECT
                dgi.id::text AS installation_id,
                dgi.discord_guild_id,
                diag.id::text AS instance_access_grant_id,
                diag.provider_community_id::text AS community_id,
                c.name AS provider_community_name,
                gs.id::text AS game_server_id,
                gs.name AS game_server_name,
                gs.slug AS game_server_slug,
                gs.management_adapter,
                gi.id::text AS instance_id,
                gi.name AS instance_name,
                diag.channel_scope,
                diag.requested_channel_ids
            FROM discord_instance_access_grants diag
            JOIN discord_guild_installations dgi ON dgi.id = diag.discord_guild_installation_id
            JOIN communities c ON c.id = diag.provider_community_id
            JOIN game_servers gs
              ON gs.id = diag.game_server_id
             AND gs.community_id = diag.provider_community_id
            JOIN game_instances gi
              ON gi.id = diag.game_instance_id
             AND gi.game_server_id = gs.id
            WHERE dgi.discord_guild_id = %s
              AND diag.status = 'active'
              AND gi.status <> 'failed'
            """,
            (str(discord_guild_id),),
        )
    except Exception:
        return None
    if channel_id is None:
        matches = rows
    else:
        channel_id = str(channel_id)
        exact = [row for row in rows if row["channel_scope"] == "allowlist" and channel_id in (row["requested_channel_ids"] or [])]
        fallback = [row for row in rows if row["channel_scope"] == "all"]
        matches = exact if exact else fallback
    # Never guess between two hosted games. A conflicting route must be fixed
    # by a Discord administrator before Trog will expose either game's data.
    if len(matches) != 1:
        return None
    row = matches[0]
    display_name = f"{row['provider_community_name']} - {row['instance_name']}"
    return DiscordContext(
        installation_id=row["installation_id"],
        guild_id=row["discord_guild_id"],
        community_id=row["community_id"],
        game_server_id=row["game_server_id"],
        game_server_name=display_name,
        game_server_slug=row["game_server_slug"],
        management_adapter=row["management_adapter"],
        instance_access_grant_id=row["instance_access_grant_id"],
        instance_id=row["instance_id"],
        instance_name=row["instance_name"],
        provider_community_name=row["provider_community_name"],
        channel_scope=row["channel_scope"] or "all",
        allowed_channel_ids=tuple(str(value) for value in (row["requested_channel_ids"] or [])),
    )


def instance_access_tables_available(conn) -> bool:
    try:
        row = fetch_one(conn, "SELECT to_regclass('discord_instance_access_grants') AS table_name")
    except Exception:
        return False
    return bool(row and row["table_name"])


def resolve_identity(conn, discord_user_id: str, community_id: str) -> DiscordIdentity:
    row = fetch_one(
        conn,
        """
        SELECT di.discord_user_id, di.user_id::text,
               cm.id::text AS membership_id, cm.role
        FROM discord_identities di
        LEFT JOIN community_memberships cm
          ON cm.user_id = di.user_id AND cm.community_id = %s
        WHERE di.discord_user_id = %s
        """,
        (community_id, str(discord_user_id)),
    )
    if not row:
        return DiscordIdentity(str(discord_user_id), None, None, None)
    return DiscordIdentity(row["discord_user_id"], row["user_id"], row["membership_id"], row["role"])


def channel_enabled(conn, context: DiscordContext, channel_id: str, category: str) -> bool:
    if context.instance_access_grant_id:
        return context.channel_scope == "all" or str(channel_id) in context.allowed_channel_ids
    row = fetch_one(
        conn,
        """
        SELECT enabled
        FROM discord_channel_policies
        WHERE discord_guild_installation_id = %s
          AND discord_channel_id = %s
          AND capability_category = %s
        """,
        (context.installation_id, str(channel_id), category),
    )
    if row is None and context.channel_scope == "allowlist":
        return False
    # No policy preserves existing guild-wide behavior unless the grant chose allowlist scope.
    return True if row is None else bool(row["enabled"])


def grant_capability_enabled(conn, context: DiscordContext, capability: str) -> bool:
    if not context.instance_access_grant_id:
        return True
    row = fetch_one(
        conn,
        """
        SELECT id::text
        FROM discord_instance_access_grant_capabilities
        WHERE discord_instance_access_grant_id = %s
          AND capability = %s
          AND revoked_at IS NULL
        """,
        (context.instance_access_grant_id, capability),
    )
    return bool(row)


def authorize(conn, guild_id: str, channel_id: str, discord_user_id: str, capability: str) -> AuthorizationDecision:
    context = resolve_guild(conn, guild_id, channel_id)
    if not context:
        reason = "channel_unmapped" if has_instance_access_grant(conn, guild_id) else "guild_not_connected"
        return AuthorizationDecision(False, reason, capability, None)
    category = "read" if capability in PUBLIC_CAPABILITIES else "administrative"
    if not channel_enabled(conn, context, channel_id, category):
        return AuthorizationDecision(False, "channel_disabled", capability, context)
    if not grant_capability_enabled(conn, context, capability):
        return AuthorizationDecision(False, "capability_not_granted", capability, context)
    if capability in PUBLIC_CAPABILITIES:
        return AuthorizationDecision(True, "public_capability", capability, context)
    if capability not in ADMINISTRATIVE_CAPABILITIES:
        return AuthorizationDecision(False, "unknown_capability", capability, context)
    identity = resolve_identity(conn, discord_user_id, context.community_id)
    if not identity.user_id:
        return AuthorizationDecision(False, "identity_not_linked", capability, context, identity)
    access = {
        "membership_id": identity.membership_id,
        "role": identity.role,
        "game_server_id": context.game_server_id,
        # Preserve the exact instance selected by an instance-access grant.
        # Dropping this value could let a server-wide grant mask an incorrectly
        # scoped request and prevents instance-scoped grants from matching.
        "instance_id": context.instance_id,
    }
    if not identity.membership_id:
        return AuthorizationDecision(False, "not_a_community_member", capability, context, identity)
    allowed = can_request_capability(access, capability, conn)
    return AuthorizationDecision(allowed, "authorized" if allowed else "capability_not_granted", capability, context, identity)
