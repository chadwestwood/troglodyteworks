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

### Visitor

An anonymous person using TWE without an authenticated account.

A Visitor may browse public content and explore the platform.

A Visitor is not stored as a User record.

---

### User

A person who has created a TWE account.

A User may authenticate, manage their personal profile, and belong to zero or more Communities.

Creating a User account does not automatically create a Community Membership.

---

### Community Member

A User with an active Membership in a specific Community.

Membership is scoped to an individual Community.

Roles and permissions are granted through Community Membership rather than through the User record.

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

### World

The universal, user-facing term for one playable game environment connected to
a Community.

Use **World** throughout the website, onboarding, navigation, help text, product
copy, and conversations with customers. It deliberately replaces game-specific
or infrastructure-specific terms such as map, instance, realm, shard, save, and
server when TWE is referring to the playable environment a member opens and
uses.

Examples:

- an ARK Genesis map is a World;
- a Minecraft Enigmatica save is a World;
- a Palworld realm is a World.

A World page uses the shared TWE World experience: current status, player count,
game details, installed content, Trog access, Community members, and
permission-gated management. Provider logs and raw operation history are not
part of the member-facing World page.

### Game Instance (Internal)

An independently manageable playable environment belonging to a game server.

TWE uses Game Instance as the internal database and API term. It is called a
**World** in the user interface.

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
```

### Community Capability Grant

Represents explicit authorization for a Community Member to perform one or more approved capabilities within a Community.

Community Owners receive all approved Community Capabilities by default.

All other Community Members require explicit Community Capability Grants.
