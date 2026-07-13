# Discord Integration

## Purpose

Trog is one Discord application installed across multiple guilds. PostgreSQL records each guild's TWE Community and Game Server, immutable Discord user identities, optional TWE user links, and per-channel capability-category policy.

## Capabilities and interactions

Mention-based natural language remains available for public, read-only capabilities:

- `instance.status.read`
- `instance.players.count.read`
- `instance.players.names.read`

Structured commands provide the durable command surface:

- `/server status`
- `/server players`
- `/server restart`

Discord command visibility never grants authority. The backend resolves the guild, channel policy, immutable Discord user ID, TWE identity link, Community Membership, and Capability Grant for every administrative request.

`instance.restart.execute` is recognized and authorized, but execution is deliberately disabled. An authorized request receives an explicit not-enabled response; an unauthorized request receives a denial. Trog does not call a management adapter or RCON restart command. Future execution must create a Server Operation and follow `docs/server-operation-lifecycle.md`.

## Persistence and authorization

`discord_guild_installations` connects an immutable Discord guild ID to Trog. For provider-owned external access, `discord_instance_access_grants` is the authority: it connects one Discord installation to one provider Community, one provider-owned Game Server, one exact Game Instance, and a provider-approved read capability allowlist. `discord_identities` stores the immutable Discord user ID and may link it to one TWE user. `discord_channel_policies` enables or disables `read` or `administrative` capabilities in a channel.

No channel policy means enabled for grants with `channel_scope = all`, preserving existing guild-wide behavior. Grants with `channel_scope = allowlist` require an explicit enabled `read` policy for the channel. An explicit disabled policy denies that category in the channel. Public read capabilities do not require an identity link once the provider-approved grant is active. Administrative capabilities require a linked TWE user and Community Membership. Community owners are implicitly authorized; other members require an active, appropriately scoped `server_operation_capability_grants` record.

Discord roles are not an authority source in this slice. They may supplement a later administrator workflow, but durable TWE membership and capability grants remain authoritative.

## Administrator setup

1. Apply migrations with `backend/genesis/.venv/bin/python backend/genesis/scripts/migrate.py`.
2. Insert a `discord_guild_installations` row using the Discord guild ID and existing TWE Community and Game Server UUIDs.
3. Insert a `discord_identities` row to record a Discord user ID; set `user_id` and `linked_at` only after the link has been verified administratively.
4. Add `discord_channel_policies` only for explicit channel/category overrides.
5. For non-owners, add an active `server_operation_capability_grants` row for `instance.restart.execute` at Community or Game Server scope.
6. Invite the bot with application-command and message permissions, enable Message Content Intent for mention support, then start the service manually.

There is not yet a self-service identity-link or guild-installation UI. These records require trusted database administration.

The Mattertrala-to-LizzLive onboarding foundation adds minimal API and setup-page support for:

1. linking Mattertrala's Discord identity to his TWE account;
2. creating an external Instance Access request for Cohorts in the Wild -> Genesis;
3. proving Discord owner, Administrator, or Manage Guild authority for the LizzLive guild;
4. provider approval by a Cohorts owner or admin;
5. bot installation confirmation;
6. channel allowlist selection;
7. activation only after both provider approval and Discord-side verification/install are complete.

This flow still uses the single shared Trog Discord application. Customers never receive the platform bot token.

Migrations `0003_discord_foundation` and `0004_discord_identity_unlink` are forward-only and non-destructive. `0004` permits a deleted TWE user link to retain its historical `linked_at` value after the foreign key sets `user_id` to null. Rolling the foundation back would require explicitly dropping the three Discord tables (channel policies first, then identities/installations), which discards installation and link state; take a backup and stop Trog before any such manual rollback. Existing TWE, Community, Game Server, and Server Operation data is unaffected.

## Environment variables

Required:

```text
TROG_DISCORD_BOT_TOKEN
TWE_DATABASE_URL
```

Optional:

```text
TROG_DISCORD_LOG_LEVEL=INFO
TROG_DISCORD_GUILD_GAME_SERVER_MAP=
```

`TROG_DISCORD_GUILD_GAME_SERVER_MAP` is a temporary read-only compatibility fallback for guilds not yet migrated to database-backed Instance Access Grants. PostgreSQL is checked first. If a guild has a pending, active, denied, or revoked Instance Access Grant, Trog does not fall back to the legacy Game Server map. The fallback never authorizes `/server restart` and should be removed after all installations are migrated and database integration tests pass reliably.

Status and player queries continue using the existing `local_asa` Management Adapter and RCON player service configuration. Tokens, RCON credentials, passwords, and session secrets must never be logged or committed.

## Runtime and logging

Run the service with:

```text
python -m twe.discord_bot.service
```

The systemd template in `deploy/systemd/trog-discord.service` is operator-managed and must not be enabled automatically. Authorization logs contain identifiers, capability/intent, and result code, but not message content or secrets. Addressed messages retain a deterministic fallback response.
