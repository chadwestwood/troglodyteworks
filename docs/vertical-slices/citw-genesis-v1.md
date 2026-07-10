# Vertical Slice: Cohorts in the Wild - Genesis (V1)

## Purpose

This document defines the first production-quality vertical slice for Troglodyte Works Experience (TWE).

Its purpose is to validate the architecture, database, authentication, navigation, Server Operations, and deterministic management workflows using a real ARK Survival Ascended environment.

This vertical slice intentionally implements a narrow but complete workflow.

Future vertical slices should build upon this foundation rather than replacing it.

---

# Goal

A community owner should be able to:

1. Visit TWE.
2. Sign in.
3. View their communities.
4. Open Cohorts in the Wild.
5. Select the ARK game server.
6. Select the Genesis game instance.
7. View instance status.
8. Execute approved Server Operations.
9. Observe deterministic progress and verification.

---

# Scope

Included:

- Authentication
- Community navigation
- Game Server navigation
- Game Instance navigation
- Instance health
- Capability discovery
- Server Operations
- PostgreSQL persistence
- Audit logging

Not included:

- Discord integration
- Payments
- Subscriptions
- Public community discovery
- Scheduled operations
- AI diagnostics
- Engineering Tracker interface

---

# User Journey

```text
Troglodyte Works

↓

Sign In

↓

My Communities

↓

Cohorts in the Wild

↓

ARK Survival Ascended

↓

Genesis

↓

Instance Dashboard

↓

Server Operation
```

---

# Navigation Rules

The user should always know where they are.

Example breadcrumb:

```text
Home
>
My Communities
>
Cohorts in the Wild
>
ARK Survival Ascended
>
Genesis
```

The current location should always be visible.

---

# Community Home

Display:

- Community name
- User role
- Available Game Servers
- Recent community activity (placeholder)
- Navigation to Members (placeholder)
- Navigation to Settings (placeholder)

Only implemented functionality needs to be active.

Future functionality may be shown but should be clearly marked as unavailable.

---

# Game Server Page

Display:

- Server name
- Game type
- Online/offline status
- Available Game Instances

Selecting an instance opens the Instance page.

---

# Genesis Instance Page

Display:

- Instance name
- Instance type
- Current health
- Current status
- Recent Server Operations
- Available capabilities

---

# Initial Capabilities

Implement only:

- Check Status
- List Players (placeholder)
- Save World (placeholder)
- Restart Instance

Placeholders should clearly indicate functionality planned but not yet implemented.

---

# Restart Workflow

Selecting Restart Instance should:

1. Ask for confirmation.
2. Create a Server Operation.
3. Display operation progress.
4. Execute deterministic restart workflow.
5. Perform health verification.
6. Display final result.

The browser must never execute operating-system commands directly.

---

# Health Verification

Minimum checks:

- expected process running
- expected network port responding
- game query successful

Health checks should be deterministic.

No AI should be required.

---

# Operation History

Display recent Server Operations.

Each operation should include:

- capability
- status
- requested by
- requested at
- completed at
- duration

---

# Initial Database Objects

Seed:

Community

```text
Cohorts in the Wild
```

Game Server

```text
ARK Survival Ascended
```

Game Instance

```text
Genesis
```

Community Membership

```text
Owner
```

---

# Authentication

Only authenticated users may access communities.

Only authorized users may execute Server Operations.

---

# User Experience

The interface should prioritize clarity over density.

The first goal is confidence.

Users should immediately understand:

- where they are
- what they can manage
- what the current health is
- what operations are available

---

# Success Criteria

The vertical slice is complete when a user can:

✓ Sign in

✓ Navigate to their community

✓ Open the ARK Game Server

✓ Open the Genesis Instance

✓ View deterministic health

✓ Create a Restart Server Operation

✓ Observe operation progress

✓ Receive verified completion

All data should persist in PostgreSQL.

---

# Out of Scope

This document does not define:

- database schema
- REST API
- authentication internals
- management adapter implementation
- UI styling
- engineering tracker
- AI diagnostics

Refer to the appropriate engineering documents for those concerns.

---

# Final Principle

This vertical slice establishes the architectural pattern for future TWE development.

Every future feature should extend this workflow rather than bypass it.
