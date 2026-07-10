# TWE Glossary

## Purpose

This document defines the shared vocabulary used throughout Troglodyte Works Experience.

Codex, future contributors, agents, documentation, database models, APIs, and user interfaces should use these terms consistently.

When a term in another document conflicts with this glossary, the conflict should be resolved before implementation continues.

---

## Platform Terms

### TWE

Troglodyte Works Experience.

The platform for managing communities, hosted game environments, engineering work, and related services.

### Platform

The complete TWE system, including community features, hosting features, engineering tools, authentication, storage, and integrations.

### Domain

A group of related business concepts with a shared purpose.

Current domains include:

- Community
- Hosting
- Engineering
- Platform

---

## Community Domain

### User

A person with a TWE account.

A user may belong to multiple communities and may own multiple communities.

### Community

A persistent social and organizational space within TWE.

A community may exist with or without hosted game services.

Examples:

- Cohorts in the Wild
- A private family gaming group
- A classroom community

### Community Membership

The relationship connecting a user to a community.

A membership includes the user’s role and permissions within that community.

### Role

The level of authority a user has within a community.

Initial roles:

- owner
- admin
- moderator
- member

### Invite

A controlled method for adding a user to a community.

An invite may lead directly to a specific destination, such as an instance or event, while still granting access to the wider community according to the assigned role.

### Deep Link

A link that opens a specific destination inside TWE rather than only opening a general landing page.

A deep link should place the user where they intended to go without trapping them there.

---

## Hosting Domain

### Game Server

A logical hosting environment for a specific game within a community.

A game server may contain one or more game instances.

Examples:

- Cohorts in the Wild ARK Server
- Cohorts Minecraft Server

A game server is a product-level concept and does not necessarily represent one operating-system process.

### Game Instance

An independently manageable playable environment belonging to a game server.

TWE uses Game Instance as the universal internal term.

Game-specific interfaces may display another label.

Examples:

- ARK map
- Minecraft world
- Palworld world
- Rust server

### Instance Type

The game-specific category of a game instance.

Examples:

- map
- world
- realm
- shard
- server
- other

### Game Identifier

The internal identifier used by the game or hosting software for an instance.

Example:

```text
Genesis_WP
