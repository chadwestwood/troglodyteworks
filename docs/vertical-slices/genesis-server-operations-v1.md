# Vertical Slice: Genesis Server Operations (V1)

## Purpose

This document defines the first production Server Operations connected to the live Cohorts in the Wild Genesis ARK Survival Ascended instance.

This slice extends the existing Genesis foundation by replacing placeholder health checks and unavailable capabilities with deterministic operations against the real local ASA server.

The browser must never execute operating-system commands or receive server credentials.

---

# Goal

An authorized Community Owner should be able to:

1. Open the Genesis Game Instance.
2. Check whether Genesis is ready for players.
3. Request a world save.
4. Request a controlled restart.
5. Observe each Server Operation stage.
6. Receive an honest verified result.

---

# Target Environment

Community:

```text
Cohorts in the Wild
```

Game Server:

```text
ARK Survival Ascended
```

Game Instance:

```text
Genesis
```

Game identifier:

```text
Genesis_WP
```

Management Adapter:

```text
local_asa
```

Current ASA installation is expected under:

```text
/opt/asa-server
```

Codex must inspect the existing ASA process, scripts, ports, logs, and RCON configuration before implementing commands.

Documentation or remembered command paths must not substitute for inspection of the actual host.

---

# Architecture

```text
Browser

↓

TWE API

↓

Server Operation

↓

local_asa Management Adapter

├── Local process controls
├── Network health checks
├── Game query checks
└── RCON commands

↓

Genesis ASA Instance
```

The Management Adapter is the only layer permitted to interact with the local ASA runtime.

---

# Initial Capabilities

Implement:

- `instance.status`
- `instance.save`
- `instance.restart`

The following may remain unavailable:

- `instance.players.list`

`instance.players.list` may be implemented only if the current RCON or game-query interface supports it reliably within this slice.

---

# Capability: Check Status

Capability key:

```text
instance.status
```

This operation must perform deterministic checks.

Required checks:

1. `process_running`
2. `port_reachable`
3. `broadcasting`

Possible additional checks:

- `rcon_reachable`
- `save_directory_accessible`

A successful process check alone does not mean the Instance is ready.

The operation may report:

- `ready`
- `degraded`
- `offline`
- `failed`
- `unknown`

The operation must not report `ready` unless every required readiness check passes.

---

# Process Check

The adapter must detect the real Genesis ASA process without matching the health-check command itself.

The check should identify the expected ASA server process and confirm that it belongs to the configured Genesis runtime.

Public API responses must not expose:

- full process command lines
- credentials
- sensitive launch arguments
- filesystem secrets

Safe internal diagnostics may be written to protected logs.

---

# Port Check

The adapter must verify the configured Genesis network endpoint.

Configuration must come from environment variables or approved adapter configuration.

The API must not depend on hard-coded ports scattered through application code.

A reachable port does not by itself prove that the game server is ready.

---

# Broadcasting Check

The adapter must determine whether Genesis is queryable or advertising itself as available.

This check should use an established deterministic game-query method.

If no reliable query method is configured, the check must return:

```text
not_configured
```

It must not report success based only on the process or port checks.

---

# Capability: Save World

Capability key:

```text
instance.save
```

The save operation should use the approved ASA administrative interface, preferably RCON when available.

Expected workflow:

```text
SO requested

↓

Validate authorization

↓

Validate adapter configuration

↓

Send save command

↓

Confirm command acceptance

↓

Record result

↓

Complete or fail
```

The operation must not accept an arbitrary command from the browser.

The RCON password must come from protected environment configuration.

The RCON password must never appear in:

- API responses
- logs
- source control
- Server Operation result messages

---

# Capability: Restart Instance

Capability key:

```text
instance.restart
```

Restart requires explicit confirmation.

Expected workflow:

```text
SO requested

↓

Save world

↓

Confirm save command acceptance

↓

Stop Genesis

↓

Verify process stopped

↓

Start Genesis

↓

Verify process running

↓

Verify port reachable

↓

Verify broadcasting

↓

Mark completed
```

A restart must not be marked completed merely because the start command returned successfully.

---

# Restart Stages

The restart Server Operation should be able to display:

- `save_requested`
- `save_confirmed`
- `stop_requested`
- `process_stopped`
- `start_requested`
- `process_running`
- `port_reachable`
- `broadcasting`
- `completed`

If a required stage fails:

- stop the workflow when continuing would be unsafe
- record the failed stage
- record a useful sanitized result
- mark the Server Operation as `failed`

---

# Stop Behavior

The adapter must inspect and use the safest existing shutdown mechanism.

Preferred order:

1. Approved graceful game-server shutdown interface
2. Existing reviewed local stop script
3. Controlled process termination with timeout and escalation

Codex must not invent a destructive kill command without inspecting the real runtime.

A stop is successful only after the expected Genesis process is no longer running.

---

# Start Behavior

The adapter must use the reviewed Genesis startup mechanism already present on the host.

It must not duplicate or silently replace the production start script.

A start request is successful only when the start mechanism launches without immediate failure.

The Server Operation remains incomplete until required health verification passes.

---

# Timeouts

Every wait stage must have a defined timeout.

Initial timeout categories:

- save acknowledgement
- process shutdown
- process startup
- port readiness
- broadcasting readiness

Timeout values should be configurable.

A timeout must produce a failed Server Operation with the specific failed stage.

The workflow must not wait indefinitely.

---

# Concurrency

Only one disruptive Server Operation may run against Genesis at a time.

While restart is active, reject conflicting operations such as:

- another restart
- save during shutdown
- another stop or start workflow

Return the documented conflict error.

A status check may run concurrently only when it cannot interfere with the active operation.

---

# Authorization

Server Operation authorization is based on Community ownership and explicit Capability grants.

## Owner Permissions

A Community Owner may execute every documented, approved, and currently available Server Operation Capability for Game Instances belonging to that Community.

Ownership does not permit:

- undocumented Capabilities
- unavailable Capabilities
- arbitrary commands
- Capabilities belonging to another Community

## Non-Owner Permissions

Admins, Moderators, and Members receive no Server Operation permissions automatically.

A non-owner may execute a Server Operation only when an explicit Capability grant applies to:

- the Community
- the Game Server
- or the Game Instance

The backend must enforce all Capability grants.

Hiding or displaying a button is not authorization.

## Initial Capability Defaults

| Capability | Owner | Admin | Moderator | Member |
|---|---:|---:|---:|---:|
| `instance.status` | Yes | Explicit grant required | Explicit grant required | Explicit grant required |
| `instance.players.list` | Yes | Explicit grant required | Explicit grant required | Explicit grant required |
| `instance.save` | Yes | Explicit grant required | Explicit grant required | Explicit grant required |
| `instance.restart` | Yes | Explicit grant required | Explicit grant required | Explicit grant required |

A Capability must also be supported and currently available through the active Management Adapter.

---

# Configuration

The adapter may require environment variables such as:

```text
TWE_ASA_EXPECTED_PROCESS
TWE_ASA_HEALTH_HOST
TWE_ASA_HEALTH_PORT
TWE_ASA_QUERY_PORT
TWE_ASA_RCON_HOST
TWE_ASA_RCON_PORT
TWE_ASA_RCON_PASSWORD
TWE_ASA_START_COMMAND
TWE_ASA_STOP_COMMAND
```

The final variable names should match the inspected implementation and be documented in `.env.example`.

Real secrets and production values must not be committed.

Command configuration must be restricted to trusted server-side administration.

The browser must never supply command paths.

---

# Audit Requirements

Every Server Operation must record:

- requesting User
- target Game Instance
- Capability
- requested time
- start time
- completion time
- state transitions
- individual check results
- final outcome

The audit trail should distinguish:

- user-requested operations
- scheduled operations
- system-triggered operations

Only user-requested operations are required in this slice.

---

# User Interface

The Genesis Instance page should show:

- current health
- last checked time
- available Capabilities
- unavailable Capabilities and reasons
- recent Server Operations

The Restart control must require confirmation.

The active Server Operation page should show progress without requiring the user to inspect server logs.

The interface must distinguish:

- requested
- executing
- verifying
- completed
- failed

---

# Safety Requirements

Codex must first implement and test adapter discovery and non-destructive status checks.

Before the first real restart, Codex must report:

1. the existing Genesis process identification
2. the current startup mechanism
3. the proposed shutdown mechanism
4. configured ports
5. proposed health-query method
6. exact files it will change
7. rollback procedure

Codex must stop for explicit human approval before executing the first real restart.

Automated tests must never restart the live Genesis server.

---

# Tests

At minimum, test:

- status operation with all checks passing
- status operation with process missing
- status operation with unconfigured port
- status operation with broadcasting failure
- save authorization
- restart confirmation requirement
- restart authorization
- conflicting-operation rejection
- timeout handling
- sanitized error responses
- operation stage ordering
- failed verification does not produce completed status

Use mocks or test adapters for automated destructive-operation tests.

---

# Definition of Done

This vertical slice is complete when:

- `instance.status` checks the real Genesis runtime
- `instance.save` performs an approved real save
- `instance.restart` performs an approved controlled restart
- restart includes deterministic post-start verification
- successful operations persist in PostgreSQL
- failures identify the failed stage
- the live browser displays operation progress and results
- no arbitrary command interface exists
- no secrets are exposed
- automated tests pass
- the first live restart is manually approved and observed

---

# Out of Scope

This document does not define:

- mod installation
- configuration editing
- scheduled operations
- backups or restores
- server updates
- map switching
- cluster transfers
- Discord announcements
- AI diagnostics
- arbitrary console commands

---

# Related Documentation

This document should be interpreted together with:

```text
docs/glossary.md
docs/database-schema.md
docs/authentication.md
docs/api-design.md
docs/server-operation-lifecycle.md
docs/codex-guidelines.md
docs/vertical-slices/citw-genesis-v1.md
```

The precedence defined in `docs/README.md` remains authoritative.

---

# Final Principle

A Server Operation succeeds only when the requested outcome is verified.

Running a command is not the same as managing a server safely.