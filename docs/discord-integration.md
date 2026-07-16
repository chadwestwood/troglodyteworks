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

`discord_guild_installations` connects an immutable Discord guild ID to Trog. For provider-owned external access, `discord_instance_access_grants` is the authority: it connects one Discord installation to one provider Community, one provider-owned Game Server, one exact Game Instance, and a provider-approved read capability allowlist. `user_external_identities(provider='discord')` is the provider-neutral authentication link for a TWE User. `discord_identities` stores the immutable Discord user ID for Discord/Trog authorization and is synchronized from Discord OAuth login/linking. `discord_channel_policies` enables or disables `read` or `administrative` capabilities in a channel.

No channel policy means enabled for grants with `channel_scope = all`, preserving existing guild-wide behavior. Grants with `channel_scope = allowlist` require an explicit enabled `read` policy for the channel. An explicit disabled policy denies that category in the channel. Public read capabilities do not require an identity link once the provider-approved grant is active. Administrative capabilities require a linked TWE user and Community Membership. Community owners are implicitly authorized; other members require an active, appropriately scoped `server_operation_capability_grants` record.

Discord roles are not an authority source in this slice. They may supplement a later administrator workflow, but durable TWE membership and capability grants remain authoritative.

## Verified setup workflow

1. Apply migrations with `backend/genesis/.venv/bin/python backend/genesis/scripts/migrate.py`.
2. The requester signs in, links Discord through the account OAuth callback, and joins the provider Community.
3. Discord account linking or **Refresh Discord servers** loads `/users/@me/guilds`, filters the result to servers where Discord reports owner, Administrator, or Manage Guild authority, and stores a one-hour verification snapshot. OAuth access and refresh tokens are not retained.
4. The requester selects the exact provider-owned Instance and a verified consumer Discord guild by name, plus optional channel scope. The browser never requires a pasted guild ID.
5. TWE redirects through the dedicated Discord installation OAuth callback and re-verifies the selected immutable guild ID before continuing.
6. Discord installs the shared Trog application into that fixed guild. TWE calls Discord with the platform bot token and records installation only after Discord confirms Trog is a member of that same guild.
7. A provider Community owner or admin approves or denies the request in the Trog Access Requests view. Approval selects the read capability allowlist and channel scope.
8. The grant becomes active only after provider approval, verified Discord authority, and verified bot installation all exist. A provider owner or admin can later revoke it.

Self-service Discord account linking now exists in Account Settings and through the Trog request page. Guild installation and provider approval still require the Instance Access Grant workflow; linking Discord by itself grants no Community membership, provider approval, instance capability, Trog installation access, or ownership.

The Mattertrala-to-LizzLive onboarding workflow provides:

1. linking Mattertrala's Discord identity to his TWE account;
2. creating an external Instance Access request for Cohorts in the Wild -> Genesis;
3. server-side proof from Discord of owner, Administrator, or Manage Guild authority for the LizzLive guild;
4. provider approval by a Cohorts owner or admin;
5. bot installation confirmation through Discord's bot API;
6. channel allowlist selection;
7. activation only after both provider approval and Discord-side verification/install are complete.

This flow still uses the single shared Trog Discord application. Customers never receive the platform bot token.

The workflow does not accept browser-supplied Discord user IDs, permission bitfields, guild names, or installation confirmation. Migration `0008_discord_verified_installation` is additive and backward compatible; it adds PKCE/guild binding to installation OAuth state and persists requested channel IDs. Existing TWE, Community, Game Server, and Server Operation data is unaffected.

## Environment variables

Required:

```text
TROG_DISCORD_BOT_TOKEN
TROG_DISCORD_CLIENT_ID
TROG_DISCORD_CLIENT_SECRET
TROG_DISCORD_REDIRECT_URI
TROG_DISCORD_INSTALL_REDIRECT_URI
TWE_DATABASE_URL
```

Optional:

```text
TROG_DISCORD_LOG_LEVEL=INFO
TROG_DISCORD_GUILD_GAME_SERVER_MAP=
```

`TROG_DISCORD_GUILD_GAME_SERVER_MAP` is a temporary read-only compatibility fallback for guilds not yet migrated to database-backed Instance Access Grants. PostgreSQL is checked first. If a guild has a pending, active, denied, or revoked Instance Access Grant, Trog does not fall back to the legacy Game Server map. The fallback never authorizes `/server restart` and should be removed after all installations are migrated and database integration tests pass reliably.

Status and player queries continue using the existing `local_asa` Management Adapter and RCON player service configuration. Player-list replies expose only the username parsed from each `ListPlayers` row; the RCON row number and immutable platform account ID are discarded before the Discord reply is built. The `what mods are installed?` mention and `/server mods` command use `instance.mods.names.read`; the adapter reads active mod IDs from `TWE_ASA_PANEL_CONFIG_PATH` and resolves names from local catalogs without making a network request per message. Tokens, RCON credentials, passwords, and session secrets must never be logged or committed.

`TROG_DISCORD_REDIRECT_URI` is the account sign-in/link callback. `TROG_DISCORD_INSTALL_REDIRECT_URI` is the separate guild verification and bot-install callback and must end at `/api/v1/discord/oauth/callback`. Register both exact URLs in the Discord Developer Portal.

Both Discord token-exchange paths send the platform Discord User-Agent. A
failed guild-verification exchange redirects back to the request page with a
recoverable error, and the pending request exposes a **Verify Discord server**
retry action instead of requiring a duplicate access request.

## Runtime and logging

Run the service with:

```text
python -m twe.discord_bot.service
```

The systemd template in `deploy/systemd/trog-discord.service` is operator-managed and must not be enabled automatically. Authorization logs contain identifiers, capability/intent, and result code, but not message content or secrets. Addressed messages retain a deterministic fallback response.
