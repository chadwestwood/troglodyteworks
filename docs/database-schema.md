# TWE Database Schema

## Purpose

This document defines the core business entities and relationships for Troglodyte Works Experience.

It is the source of truth for future PostgreSQL migrations and application models.

## Core Relationships

- A user may belong to multiple communities.
- A user may own multiple communities.
- A community may have multiple users.
- A community may have multiple game servers.
- A game server may have multiple instances.
- An instance represents a playable space such as an ARK map or Minecraft world.
- A user may authenticate through local credentials and multiple external identities.

## Entities

### User

Represents a person with a TWE account.

Fields:

- id
- email
- password_hash
- display_name
- created_at
- updated_at

`password_hash` may be null when the User was created through an external provider and has not configured a local password.

### External Identity

Links one immutable external provider identity to one TWE User.

Fields: `id`, `user_id`, `provider`, `provider_subject`, `provider_username`, `provider_email`, `provider_email_verified`, `linked_at`, `last_authenticated_at`, `created_at`, `updated_at`.

Supported providers in this slice are `google` and `discord`. `(provider, provider_subject)` is unique. `(user_id, provider)` is unique. Provider email is metadata and must not be treated as proof of account ownership.

### OAuth State

Stores one-time OAuth login/link state.

Fields: `state_hash`, `provider`, `purpose`, `user_id`, `redirect_path`, `code_verifier`, `nonce`, `nonce_hash`, `created_at`, `expires_at`, `consumed_at`.

Purposes are `login` and `link`. Link states are bound to the signed-in TWE User. Redirect paths are same-origin relative paths only.

### Community

Represents a persistent social and organizational space.

Fields:

- id
- name
- slug
- description
- created_by
- created_at
- updated_at

### Community Membership

Connects a user to a community.

Fields:

- id
- user_id
- community_id
- role
- joined_at

Possible roles:

- owner
- admin
- moderator
- member

### Community Invitation

Represents an invitation to join one Community.

Fields: `id`, `community_id`, `invitation_type`, `invited_user_id`, `token_hash`, `initial_role`, `requires_approval`, `maximum_uses`, `use_count`, `expires_at`, `status`, `created_by_user_id`, `revoked_by_user_id`, `created_at`, `updated_at`, `revoked_at`.

Invitation types are `direct` and `link`. Direct invitations target one existing TWE user. Link invitations store only a secure hash of the random token, never the plaintext token.

Accepting an invitation creates basic Community Membership only. It does not grant server operation, instance access, Discord installation approval, or ownership.

### Community Invitation Redemption

Records a user's response to a Community Invitation.

Fields: `id`, `invitation_id`, `user_id`, `status`, `redeemed_at`, `approved_by_user_id`, `approved_at`, `denied_by_user_id`, `denied_at`.

Statuses are `accepted`, `declined`, `pending_approval`, `approved`, and `denied`.

### Server Operation Capability Grant

Represents explicit permission for a non-owner Community Member to execute one or more approved Server Operation Capabilities.

Fields:

- id
- community_membership_id
- capability
- game_server_id (optional)
- game_instance_id (optional)
- granted_by
- created_at
- revoked_at (optional)

Rules:

- Community Owners do not require Capability Grant records.
- Non-owner Community Members receive no Server Operation permissions by default.
- A Capability Grant may apply to:
  - an entire Community
  - a specific Game Server
  - a specific Game Instance
- A revoked grant no longer authorizes execution.
- A granted Capability must still be documented, supported, and available through the active Management Adapter.

### Discord Guild Installation

Connects one immutable Discord guild ID to an existing Community and Game Server.

Fields: `id`, `discord_guild_id`, `community_id`, `game_server_id`, `installed_by`, `created_at`, `updated_at`.

The guild ID is unique numeric text so its external representation is not subject to platform integer limits. The Game Server must belong to the same Community; application resolution enforces this relationship.

### Discord Identity

Records one immutable Discord user ID and an optional verified link to a TWE User.

Fields: `id`, `discord_user_id`, `user_id`, `created_at`, `linked_at`, `updated_at`.

Discord user IDs and linked TWE user IDs are unique. Unlinked identities provide a durable path for a later verification workflow without granting authority.

For authentication and account linking, the provider-neutral `user_external_identities` table is authoritative. `discord_identities` remains Discord integration metadata used by Trog authorization and is synchronized when Discord OAuth login/linking succeeds.

### Discord Channel Policy

Enables or disables Trog capability categories for one channel in an installed guild.

Fields: `id`, `discord_guild_installation_id`, `discord_channel_id`, `capability_category`, `enabled`, `created_at`, `updated_at`.

Categories in this slice are `read` and `administrative`. The installation, channel, and category tuple is unique. Absence of a policy preserves enabled guild-wide compatibility behavior.

### Discord Instance Access Grant

Represents provider-approved Discord access to one exact provider-owned Game Instance.

Fields: `id`, `discord_guild_installation_id`, `provider_community_id`, `game_server_id`, `game_instance_id`, `requested_by`, `requester_discord_user_id`, `consumer_discord_guild_id`, `consumer_discord_guild_name`, `status`, `channel_scope`, `requested_channel_ids`, approval timestamps, installation timestamps, denial/revocation timestamps, `created_at`, `updated_at`.

Statuses in this slice are `pending_discord_verification`, `pending_provider_approval`, `pending_bot_installation`, `active`, `denied`, `revoked`, and `configuration_error`.

The provider Community must own the Game Server, and the Game Server must contain the exact Game Instance. The migration enforces this with composite foreign keys. A Discord guild consumes the approved capabilities; it does not become a TWE Community and does not gain ownership.

### Discord Instance Access Grant Capability

Stores the provider-approved read capability allowlist for one Instance Access Grant.

Fields: `id`, `discord_instance_access_grant_id`, `capability`, `granted_by`, `created_at`, `revoked_at`.

Allowed values are `instance.status.read`, `instance.players.count.read`, `instance.players.names.read`, and `instance.mods.names.read`. A revoked capability no longer authorizes Discord reads. Migration `0009_discord_mod_names_capability.sql` adds the mod-name capability and backfills only grants that had already been provider-approved for the complete original read bundle.

### Discord Guild Authority Verification

Records that a linked TWE user proved Discord authority for a consumer guild during the onboarding flow.

Fields: `id`, `user_id`, `discord_user_id`, `discord_guild_id`, `discord_guild_name`, `can_manage_guild`, `authority_source`, `verified_at`, `expires_at`.

Authority sources are `owner`, `administrator`, and `manage_guild`. Discord account linking or refresh stores a one-hour snapshot used to populate the verified server dropdown; the dedicated installation flow re-verifies the selected guild before use. This verification proves Discord-side installation authority only; it does not grant provider Community ownership or server administration.

### Discord Installation OAuth State

Stores one-time, expiring state for guild verification or bot installation. The state is bound to the authenticated TWE User, Instance Access Grant, purpose, PKCE verifier, and selected immutable Discord guild ID. It is consumed before an authorization result is applied and cannot be reused.
### Game Server

Represents a logical game environment belonging to a community.

Fields:

- id
- community_id
- name
- slug
- game_type
- management_adapter
- status
- created_at
- updated_at

### Game Instance

Represents a playable space managed under a game server.

Examples include:

- ARK map
- Minecraft world
- Palworld world
- other game-specific environments

Fields:

- id
- game_server_id
- name
- slug
- instance_type
- game_identifier
- status
- sort_order
- created_at
- updated_at

### Server Operation

Represents a recorded execution of a Capability against a specific Game Instance.

A Server Operation records the complete lifecycle of requested work, including execution, verification, and final outcome.

Fields:

- id
- game_instance_id
- requested_by
- capability
- status
- current_stage
- requested_at
- started_at
- completed_at
- result_message

Initial statuses:

- requested
- queued
- executing
- verifying
- completed
- failed
- cancelled

A Server Operation may have multiple stage or health-check records so that execution and verification progress can be displayed.

### Server Operation Check

Represents one deterministic execution or verification check belonging to a Server Operation.

Fields:

- id
- server_operation_id
- name
- status
- started_at
- completed_at
- result_message
- sort_order

Initial check statuses:

- pending
- running
- passed
- failed
- skipped

## Initial Seed Data

### User

- display_name: Chad
- role: application administrator

### Community

- name: Cohorts in the Wild
- slug: cohorts-in-the-wild

### Membership

- user: Chad
- community: Cohorts in the Wild
- role: owner

### Game Server

- name: Cohorts in the Wild
- game_type: ARK Survival Ascended
- management_adapter: local_asa

### Game Instance

- name: Genesis
- instance_type: map
- game_identifier: Genesis_WP
