# Trog Bot Workflow

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
```

For external provider-owned access, replies identify the provider-owned instance:

```text
Cohorts in the Wild - Genesis is up and ready for players.
```

Trog must not describe the instance as owned by the consumer Discord guild.
