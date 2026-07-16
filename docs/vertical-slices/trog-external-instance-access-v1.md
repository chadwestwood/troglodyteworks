# Vertical Slice: Provider-Owned Instance Discord Access (V1)

## Purpose

This document defines the next Trog Discord vertical slice: provider-owned, instance-specific, read-only Discord access.

A TWE Community that owns a Game Instance can authorize Trog to expose selected read-only capabilities for that exact Instance inside a consumer Discord guild. The Discord guild consumes selected capabilities; it does not become the owner of the Instance, Game Server, or provider Community.

Concrete target example:

```text
Provider Community: Cohorts in the Wild
Game Server: ARK Survival Ascended
Instance: Genesis
Consumer Discord Guild: LizzLive
Relationship: Cohorts in the Wild -> Genesis -> LizzLive Discord
```

The same model also supports the existing Cohorts Discord guild pointing to the same Cohorts-owned Genesis Instance.

## Goal

A provider Community Owner should be able to approve read-only Trog access for one exact provider-owned Instance in one Discord guild.

The Discord guild administrator must separately authorize Trog installation in that guild. The installation becomes usable only after both approvals exist.

Initial exposed capabilities:

- `instance.status.read`
- `instance.players.count.read`
- `instance.players.names.read`
- `instance.mods.names.read`

Unavailable in this slice:

- restart
- save
- stop/start
- mod management
- configuration changes
- file access
- administrative Server Operations
- multi-instance selection inside one Discord guild

## Domain Model

Use these terms consistently:

- Provider Community: the TWE Community that owns or controls the exposed Instance.
- Consumer Discord Guild: the Discord guild where Trog responds.
- Discord Installation: the durable record for Trog being connected to an immutable Discord guild ID.
- Instance Access Grant: the provider-approved relationship exposing one exact Instance to one Discord Installation.
- Exposed Capabilities: the provider-approved capability allowlist for the grant.
- Channel Policy: optional Discord channel scope for allowed capabilities.

Do not describe this as community friendship. A separate LizzLive TWE Community may exist, but it does not own Cohorts in the Wild's Genesis Instance unless a separate ownership model explicitly says so.

Desired relationship:

```text
Provider Community
owns
Game Server
contains
Instance
exposed through
Instance Access Grant
consumed by
Discord Guild Installation
scoped by
Channel Policy and Capability Allowlist
```

"Instance" is the universal TWE concept. For ARK Survival Ascended, an Instance corresponds to a playable map such as Genesis.

## Implemented V1 Boundary

Discord reads now resolve through an exact active Instance Access Grant. Account linking or refresh supplies a short-lived managed-guild dropdown, guild authority is re-verified from Discord OAuth managed-guild data, installation is bound to the selected fixed guild in the Discord authorization URL, and TWE confirms bot membership with Discord before persisting installation. The browser cannot directly assert a Discord identity, permission bitfield, guild name, guild ID, or completed installation. `TROG_DISCORD_GUILD_GAME_SERVER_MAP` remains only as a temporary read-only migration fallback for installations with no grant record.

## Resolution Rule

Every Discord status or player request must resolve exactly one configured Instance:

```text
Discord guild
-> channel policy
-> active Discord installation and active Instance Access Grant
-> provider Community
-> exact Instance
-> owning Game Server
-> management adapter
```

Required behavior:

- Trog must never choose a default Instance, first Instance, first server, or arbitrary map.
- If no active grant exists, return `guild_not_connected`.
- If the grant has no Instance, return `instance_not_configured`.
- If the configured Instance no longer exists or is inactive, return `instance_unavailable`.
- If more than one active grant could serve the same guild/channel in this slice, return `ambiguous_instance_mapping`.
- Responses must identify the provider-owned Instance, for example `Cohorts in the Wild - Genesis is up and ready for players.`
- Responses must not imply that LizzLive owns Genesis.

## Schema Contract

Create a forward-only migration after the currently applied Discord migrations. Do not modify existing applied migrations.

Proposed migration name:

```text
backend/genesis/migrations/0005_discord_instance_access_grants.sql
```

Minimum durable schema:

### Discord Instance Access Grant

New table: `discord_instance_access_grants`

Fields:

- `id`
- `discord_guild_installation_id`
- `provider_community_id`
- `game_server_id`
- `game_instance_id`
- `status`
- `channel_scope`
- `requested_by`
- `provider_approved_by`
- `provider_approved_at`
- `discord_approved_by`
- `discord_approver_user_id`
- `discord_approved_at`
- `activated_at`
- `revoked_by`
- `revoked_at`
- `created_at`
- `updated_at`

Status values:

- `pending`
- `active`
- `revoked`

Channel scope values:

- `all`
- `allowlist`

Required constraints:

- Discord guild IDs and Discord user IDs remain immutable numeric text.
- `provider_community_id` must reference `communities(id)`.
- `game_server_id` must reference `game_servers(id)`.
- `game_instance_id` must reference `game_instances(id)`.
- The database must prove the ownership chain:
  - `game_servers(id, community_id)` matches `(game_server_id, provider_community_id)`.
  - `game_instances(id, game_server_id)` matches `(game_instance_id, game_server_id)`.
- An `active` grant must have both provider approval and Discord approval timestamps.
- A `revoked` grant must have `revoked_at`.
- At most one active grant may exist per Discord installation for this slice.
- Add lookup indexes for installation, provider Community, Game Server, Game Instance, and active status.

The existing `discord_guild_installations.community_id` and `discord_guild_installations.game_server_id` fields remain for compatibility during migration, but the new resolver must treat the Instance Access Grant as the authority for Discord read access.

### Discord Instance Access Grant Capability

New table: `discord_instance_access_grant_capabilities`

Fields:

- `id`
- `discord_instance_access_grant_id`
- `capability`
- `granted_by`
- `created_at`
- `revoked_at`

Initial allowed capability values:

- `instance.status.read`
- `instance.players.count.read`
- `instance.players.names.read`
- `instance.mods.names.read`

Required constraints:

- Capability rows must reference an existing Instance Access Grant.
- Only the initial read capabilities may be inserted in this slice.
- A grant and capability may have only one active row at a time.
- Revoked capabilities no longer authorize requests.

### Channel Policy

Reuse `discord_channel_policies` for this slice.

Rules:

- `channel_scope = all`: no channel policy means read access is enabled guild-wide, preserving current behavior.
- `channel_scope = allowlist`: only channels with an explicit enabled `read` policy are allowed.
- An explicit disabled `read` policy denies that channel.
- Administrative channel policies do not grant administrative capability in this slice.

Future multi-instance support may require grant-specific channel policies. Do not implement that in V1.

## Backend Workflow

Minimum setup flow:

1. A Discord administrator creates or signs into a TWE account.
2. If the administrator used Google or local credentials first, the administrator connects Discord to the same TWE User through `docs/vertical-slices/multi-provider-authentication-and-account-linking-v1.md`.
3. The administrator joins the provider Community, such as Cohorts in the Wild. This membership may be established through `docs/vertical-slices/community-invitation-membership-v1.md`.
4. The administrator requests access for one exact provider-owned Instance and one Discord guild they manage.
5. TWE verifies the requested Instance belongs to the provider Community.
6. A provider Community Owner or authorized manager approves:
   - exact Instance;
   - exact read capabilities;
   - optional channel scope.
7. The Discord administrator completes the Trog installation flow.
8. TWE verifies that the approving Discord user can manage the selected Discord guild.
9. The grant becomes active only after provider approval and Discord installation approval both exist.
10. The Trog request view displays provider Community, Instance, Discord guild, channels, exposed capabilities, and status, with provider approve, deny, and revoke controls.

The request page implements the minimum requester and provider management surface. Durable objects and all approval checks remain server-side.

Implemented API shape:

```text
GET  /api/v1/discord/managed-guilds
POST /api/v1/discord/instance-access-requests
GET  /api/v1/discord/instance-access-requests/{id}
POST /api/v1/discord/instance-access-requests/{id}/oauth-state
GET  /api/v1/discord/oauth/callback
POST /api/v1/discord/instance-access-requests/{id}/provider-approval
POST /api/v1/discord/instance-access-requests/{id}/provider-denial
POST /api/v1/discord/instance-access-grants/{id}/revoke
GET  /api/v1/discord/installations
```

API responses must not expose bot tokens, RCON credentials, provider secrets, or private environment values.

## Bot Behavior

Preserve mention support:

```text
@Trog is the server up?
@Trog how many players are online?
@Trog who's on?
@Trog what mods are installed?
```

Supported slash commands remain:

```text
/server status
/server players
/server mods
```

`/server restart` must remain denied or explicitly not enabled for this external read-only grant.

Example responses:

```text
Cohorts in the Wild - Genesis is up and ready for players.
```

```text
Cohorts in the Wild - Genesis currently has 3 players online:
- PlayerOne
- PlayerTwo
- PlayerThree
```

The display name should come from the resolved provider Community and exact Instance. The consumer Discord guild name is audit context, not ownership context.

## Authorization Rules

Public Discord users in an enabled channel may use only active capabilities granted to that Discord installation.

Rules:

- A Discord installation does not create TWE Community membership.
- A Discord guild administrator cannot expand provider-approved capabilities.
- Joining the provider Community does not approve an external Discord installation.
- Provider Community membership alone does not authorize exposing an Instance; the separate provider-approved Instance Access Grant is still required.
- Provider owners may revoke the grant.
- Provider owners may revoke or reduce capabilities.
- All authorization decisions must be server-side.
- Discord roles and command visibility may improve UX, but they are never sufficient authority.
- Environment fallback remains read-only and cannot grant ownership, membership, or administrative access.

Log authorization decisions with:

- provider Community ID;
- Instance ID;
- Discord guild ID;
- Discord channel ID;
- requester Discord user ID;
- requested capability;
- authorization result.

Do not log message content unnecessarily. Never log secrets.

## Existing Cohorts Migration

Preserve the currently working Cohorts Discord integration while migrating.

Migration path:

1. Keep `TROG_DISCORD_GUILD_GAME_SERVER_MAP` available as a read-only compatibility fallback.
2. Resolve the existing Cohorts Discord guild ID from trusted configuration or Discord admin records. Do not invent or guess it.
3. Resolve `Cohorts in the Wild -> ARK Survival Ascended -> Genesis` from PostgreSQL.
4. Stop if the query does not return exactly one active Instance.
5. Insert or update the `discord_guild_installations` row for that immutable Discord guild ID.
6. Insert a pending `discord_instance_access_grants` row for Cohorts-owned Genesis.
7. Record provider approval by a Cohorts provider owner.
8. Record Discord installation approval by a verified Discord guild administrator.
9. Insert the four read-only capability rows.
10. Activate the grant.
11. Verify status, count, player-list, and installed-mod requests use the database-backed Instance grant.
12. Remove the Cohorts guild from the environment fallback only after database-backed behavior is verified.

The live database inspected for this planning pass contains `Cohorts in the Wild -> ARK Survival Ascended -> Genesis`, but no Discord installation row should be assumed from that fact alone.

## Future LizzLive Approval

For LizzLive, the same flow creates a separate Discord Installation and Instance Access Grant:

```text
Cohorts in the Wild -> Genesis -> LizzLive Discord
```

Important outcomes:

- LizzLive Discord users can read only the provider-approved capabilities.
- LizzLive does not own Genesis.
- LizzLive does not gain Cohorts Community membership.
- Cohorts can revoke LizzLive access without deleting either Community or Discord installation.
- Cohorts Discord and LizzLive Discord can both point to the same Cohorts-owned Genesis Instance through independent grants.

## Tests

Add or update tests for:

- provider Community owns the configured Instance;
- LizzLive Discord can read Cohorts Genesis status through an active grant;
- LizzLive does not become owner of Genesis;
- Cohorts Discord and LizzLive Discord can independently point to the same Genesis Instance;
- revoked grant denies access;
- missing provider approval remains inactive;
- missing Discord approval remains inactive;
- Discord guild administrator cannot expand capabilities;
- wrong Instance or cross-Community ownership is rejected;
- missing Instance returns `instance_not_configured`;
- inactive or deleted Instance returns `instance_unavailable`;
- ambiguous mappings fail with `ambiguous_instance_mapping`;
- existing status, count, and player-list behavior remains working;
- read-only environment fallback still works until migrated;
- environment fallback does not authorize restart;
- full backend test suite passes.

Relevant test command:

```text
backend/genesis/.venv/bin/python -m pytest backend/genesis/tests
```

Targeted Discord test command:

```text
backend/genesis/.venv/bin/python -m pytest backend/genesis/tests/test_discord_bot.py backend/genesis/tests/test_discord_foundation_integration.py
```

## Documentation Updates Required With Implementation

When the implementation lands, update:

- `docs/trog-bot-workflow.md`
- `docs/discord-integration.md`
- `docs/database-schema.md`
- `docs/services.md`
- `docs/domain.md`
- `docs/server-operation-lifecycle.md` if any administrative Discord operation behavior changes

These updates must explicitly state that the provider TWE Community owns the Instance and that a Discord guild consumes selected capabilities.

## Operational Safety

Do not:

- expose the platform bot token to customers;
- start or enable systemd automatically;
- perform a real restart;
- grant restart/save/admin operations through this external access grant;
- commit or push without explicit user approval;
- delete the read-only fallback before all working guilds have database-backed grants;
- proceed with migration if provider ownership of the Instance cannot be proven.

## Completion Contract For Implementation

The implementation pass is complete only when it can report:

1. the final domain model;
2. schema and migration changes;
3. how the existing Cohorts Discord mapping was migrated;
4. how a future LizzLive request is approved;
5. exact APIs or setup steps added;
6. files changed;
7. tests and exact results;
8. manual database or Discord steps still required;
9. unresolved risks;
10. exact commands used to test Cohorts and then LizzLive.
