# Trog Bot Workflow

**Status:** Partially implemented

**Verified production interactions:** status, player count, and player names for the Nitrado-hosted Genesis Instance

## Purpose

Trog is the Discord-facing community assistant for Troglodyte Works.

Trog allows Discord members to interact with community and game-server capabilities without requiring them to log directly into the Troglodyte Works website.

Trog is one shared Discord application installed across multiple Discord servers. Each Discord server is connected to its own Troglodyte Works community, game servers, instances, permissions, and configuration.

---

## Core Principles

1. Trog must know who is asking.
2. Trog must know which Discord community the request came from.
3. Trog must know which provider Troglodyte Works community and exact instance are exposed to that Discord server.
4. Trog must authorize every requested capability before performing it.
5. Read-only public actions may use natural-language mentions.
6. Administrative or destructive actions should use structured slash commands.
7. Dangerous actions require confirmation.
8. Every administrative action must be auditable.
9. Discord roles may supplement authorization but must not be the only source of authority.
10. Secrets must never be stored in source control or sent through Discord messages.
11. A consumer Discord guild may receive approved read capabilities without owning the provider Community's instance.
12. Provider owners must be able to revoke external Discord access without deleting either community or installation.

---

## Supported Interaction Types

### Natural-language mentions

Examples:

```text
@Trog is the server up?
@Trog how many players are online?
@Trog who's on?
@Trog what mods are installed?  (provider capability required; not verified for Nitrado)
@Trog map settings             (combined provider capabilities required; not verified for Nitrado)
```

For external provider-owned access, replies identify the provider-owned instance:

```text
Cohorts in the Wild - Genesis is up and ready for players.
```

Installed-mod questions require `instance.mods.names.read`. The former local ASA
adapter could read its local launch list, but production Genesis now uses Nitrado.
Trog must return a clear unavailable response unless the selected provider adapter
advertises and implements that capability. This is read-only and never grants mod
management.

The `map settings` summary combines server status, online player names, and
the active mod list. Each section retains its corresponding read capability
check; the combined command does not broaden the requester's access.

Trog must not describe the instance as owned by the consumer Discord guild.

Player-list responses contain display usernames only. Provider payload fields,
RCON row numbers, immutable platform account IDs, and Nitrado service identifiers
must be removed before composing a Discord reply.

Discord account linking is handled through the provider-neutral external identity model. A User who signed up with Google or local credentials must connect Discord to the same TWE User before Discord guild authority can be verified. Linking Discord only proves the Discord user identity; Community Membership, provider approval, Instance Access Grants, and capability allowlists remain separate authorization steps.
