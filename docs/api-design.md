# TWE API Design

## Purpose

This document defines the REST API contract for Troglodyte Works Experience (TWE).

The API exposes TWE business objects and workflows to web clients, desktop clients, mobile clients, and future integrations.

This document defines the public API contract.

Implementation details belong within the application and are intentionally excluded from this specification.

---

# Design Principles

- Use REST-style resource endpoints.
- Use JSON for all requests and responses.
- Authenticate before accessing protected resources.
- Authorize every privileged action.
- Expose business concepts rather than infrastructure details.
- Server Operations are requested through the API rather than executing scripts directly.
- The API should remain stable even if the implementation changes.
- Implement only the approved vertical slice before expanding functionality.

---

# Base Path

All endpoints are rooted at:

```text
/api/v1
```

Versioning allows future API evolution without breaking existing clients.

---

# Resource Hierarchy

The API follows the TWE object model.

```text
User
    ↓
Community
    ↓
Game Server
    ↓
Game Instance
    ↓
Server Operation
```

Routes should reflect these relationships whenever practical.

---

# Authentication

Authentication determines **who** the user is.

Authorization determines **what** the user may do.

Detailed authentication and authorization rules are defined in:

```text
docs/authentication.md
```
---

## Create Account

```text
POST /api/v1/auth/register
```

Creates a new User account.

Creating an account does not automatically create a Community Membership.

### Request

```json
{
    "display_name": "Alex",
    "email": "alex@example.com",
    "password": "a-secure-password",
    "password_confirmation": "a-secure-password"
}
```

### Successful Response

```json
{
    "user": {
        "id": "user-id",
        "email": "alex@example.com",
        "display_name": "Alex"
    }
}
```

The response also establishes a secure authenticated session.

Successful registration redirects the User to **My Communities** unless an approved invite destination exists.
---

## Sign In

```text
POST /api/v1/auth/login
```

### Request

```json
{
    "email": "user@example.com",
    "password": "password"
}
```

### Successful Response

```json
{
    "user": {
        "id": "user-id",
        "email": "user@example.com",
        "display_name": "Chad"
    }
}
```

A successful sign in creates a secure server-managed session.

Passwords are never returned.

---

## Sign Out

```text
POST /api/v1/auth/logout
```

### Successful Response

```json
{
    "success": true
}
```

---

## Current User

```text
GET /api/v1/auth/me
```

Returns the currently authenticated user.

### Example

```json
{
    "user": {
        "id": "user-id",
        "email": "user@example.com",
        "display_name": "Chad"
    }
}
```
---

# Communities

## List My Communities

```text
GET /api/v1/communities
```

Returns every Community available to the authenticated user through an active Community Membership.

### Successful Response

```json
{
    "communities": [
        {
            "id": "community-id",
            "name": "Cohorts in the Wild",
            "slug": "cohorts-in-the-wild",
            "role": "owner"
        }
    ]
}
```

The response should include the authenticated user's role within each Community.

A user must not receive Communities they are not authorized to access.

---

## Get Community

```text
GET /api/v1/communities/{community_id}
```

Returns one Community when the authenticated user has an active Community Membership.

### Successful Response

## Community Invitations

```text
POST /api/v1/communities/{community_id}/invitations
GET /api/v1/communities/{community_id}/invitations
POST /api/v1/communities/{community_id}/invitations/{invitation_id}/revoke
GET /api/v1/community-invitations/{token}
POST /api/v1/community-invitations/{token}/accept
POST /api/v1/community-invitations/{token}/decline
POST /api/v1/community-invitations/direct/{invitation_id}/accept
POST /api/v1/community-invitations/direct/{invitation_id}/decline
POST /api/v1/communities/{community_id}/invitation-redemptions/{redemption_id}/approve
POST /api/v1/communities/{community_id}/invitation-redemptions/{redemption_id}/deny
```

Community Invitations let authorized Community leaders invite existing TWE users directly or create shareable links. Link tokens are returned only once on creation; later API responses never return token hashes or plaintext tokens.

Accepting an invitation grants only the configured Community role. It does not grant Game Instance access, Discord installation authority, Server Operations, restart, save, mods, or ownership.

```json
{
    "community": {
        "id": "community-id",
        "name": "Cohorts in the Wild",
        "slug": "cohorts-in-the-wild",
        "description": "A gaming community.",
        "current_user_role": "owner"
    }
}
```

### Processing Requirements

- Authenticate the user.
- Verify the Community exists.
- Verify the user has an active Community Membership.
- Return the user's current role within the Community.

---

## List Community Game Servers

```text
GET /api/v1/communities/{community_id}/game-servers
```

Returns the Game Servers belonging to the Community.

### Successful Response

```json
{
    "game_servers": [
        {
            "id": "game-server-id",
            "community_id": "community-id",
            "name": "Cohorts in the Wild",
            "slug": "cohorts-in-the-wild-ark",
            "game_type": "ARK Survival Ascended",
            "status": "online"
        }
    ]
}
```

### Processing Requirements

- Authenticate the user.
- Verify Community Membership.
- Return only Game Servers belonging to the requested Community.
- Do not expose hosting credentials or infrastructure details.

---

# Game Servers

## Get Game Server

```text
GET /api/v1/game-servers/{game_server_id}
```

Returns one Game Server.

### Successful Response

```json
{
    "game_server": {
        "id": "game-server-id",
        "community_id": "community-id",
        "name": "Cohorts in the Wild",
        "slug": "cohorts-in-the-wild-ark",
        "game_type": "ARK Survival Ascended",
        "management_adapter": "local_asa",
        "status": "online"
    }
}
```

### Processing Requirements

- Authenticate the user.
- Resolve the Game Server's Community.
- Verify the user has access to that Community.
- Return only public product-level fields.
- Do not expose command paths, credentials, ports, or secret configuration values unless a future approved contract explicitly permits them.

---

## List Game Instances

```text
GET /api/v1/game-servers/{game_server_id}/instances
```

Returns every Game Instance belonging to the Game Server that the authenticated user is permitted to view.

### Successful Response

```json
{
    "instances": [
        {
            "id": "instance-id",
            "game_server_id": "game-server-id",
            "name": "Genesis",
            "slug": "genesis",
            "instance_type": "map",
            "game_identifier": "Genesis_WP",
            "status": "online",
            "sort_order": 1
        }
    ]
}
```

---

# Game Instances

## Get Game Instance

```text
GET /api/v1/instances/{instance_id}
```

Returns one Game Instance.

### Successful Response

```json
{
    "instance": {
        "id": "instance-id",
        "game_server_id": "game-server-id",
        "name": "Genesis",
        "slug": "genesis",
        "instance_type": "map",
        "game_identifier": "Genesis_WP",
        "status": "online"
    }
}
```

### Processing Requirements

- Authenticate the user.
- Resolve the parent Game Server and Community.
- Verify the user's Community Membership.
- Return only fields permitted by the API contract.

---

## Get Instance Health

```text
GET /api/v1/instances/{instance_id}/health
```

Returns deterministic health information for the Game Instance.

Health checks must not require AI.

### Successful Response

```json
{
    "health": {
        "overall_status": "ready",
        "checked_at": "2026-07-10T15:30:00Z",
        "checks": [
            {
                "name": "process_running",
                "status": "passed",
                "message": "Expected ARK process was detected."
            },
            {
                "name": "port_reachable",
                "status": "passed",
                "message": "Expected network port responded."
            },
            {
                "name": "broadcasting",
                "status": "passed",
                "message": "The game server is queryable."
            }
        ]
    }
}
```

Possible `overall_status` values:

- `unknown`
- `offline`
- `starting`
- `degraded`
- `ready`
- `failed`

Possible health-check statuses:

- `unknown`
- `not_configured`
- `pending`
- `passed`
- `failed`

### Health Rules

- A process check alone does not prove the Instance is ready.
- An unavailable or unimplemented check must not be reported as passed.
- `ready` should only be returned when every required readiness check has passed.
- `degraded` may be returned when the process is running but one or more readiness checks have not passed.
- Health responses must not expose raw shell commands, credentials, or confidential configuration.

---

# Capability Discovery

## List Instance Capabilities

```text
GET /api/v1/instances/{instance_id}/capabilities
```

Capabilities are discovered from the active Management Adapter and filtered according to the authenticated user's authorization.

The client must never assume that a capability exists.

### Successful Response

```json
{
    "capabilities": [
        {
            "key": "instance.status",
            "name": "Check Status",
            "description": "Run deterministic health checks for this Instance.",
            "available": true,
            "requires_confirmation": false
        },
        {
            "key": "instance.restart",
            "name": "Restart Instance",
            "description": "Restart the Instance and verify that it returns to a ready state.",
            "available": false,
            "requires_confirmation": true,
            "unavailable_reason": "Live restart execution has not yet been approved."
        }
    ]
}
```

Initial capability keys:

- `instance.status`
- `instance.players.list`
- `instance.save`
- `instance.restart`

### Capability Rules

- Return only capabilities defined for the active Management Adapter.
- Filter capabilities according to the authenticated user's role.
- An unavailable capability may be returned when the interface needs to explain that it exists but is not currently usable.
- Unavailable capabilities must include a clear reason.
- The API must not expose a general-purpose shell, command, script, or arbitrary-execution capability.
- Capability discovery describes what may be requested; it does not execute the Capability.

---

# Server Operations

A Server Operation is a recorded execution of a Capability against a specific Game Instance.

The API creates, retrieves, and reports Server Operations.

The browser must never execute operating-system commands directly.

---

## Create Server Operation

```text
POST /api/v1/instances/{instance_id}/server-operations
```

### Request

```json
{
    "capability": "instance.restart",
    "confirmed": true
}
```

The `confirmed` field is required only when the Capability requires confirmation.

### Processing Requirements

- Authenticate the user.
- Resolve the Game Instance, Game Server, and Community.
- Verify active Community Membership.
- Verify the user's role permits the requested Capability.
- Verify the active Management Adapter defines the Capability.
- Verify the Capability is currently available.
- Verify confirmation when required.
- Reject conflicting operations when required.
- Create the Server Operation before execution begins.
- Record the requesting user.
- Begin or queue deterministic execution.
- Return the created Server Operation.

### Successful Response

```json
{
    "server_operation": {
        "id": "operation-id",
        "instance_id": "instance-id",
        "capability": "instance.restart",
        "status": "requested",
        "current_stage": null,
        "requested_at": "2026-07-10T15:35:00Z",
        "started_at": null,
        "completed_at": null,
        "result_message": null
    }
}
```

### Response Status

A successful creation should return:

```text
202 Accepted
```

The response confirms that the Server Operation was accepted.

It does not claim that execution has completed.

---

## Operation Confirmation

A Capability may require explicit confirmation.

Example:

```json
{
    "capability": "instance.restart",
    "confirmed": false
}
```

When confirmation is required but not supplied, return:

```json
{
    "error": {
        "code": "CONFIRMATION_REQUIRED",
        "message": "This operation requires confirmation."
    }
}
```

The API must not infer confirmation from the presence of a button click alone.

---

## List Instance Server Operations

```text
GET /api/v1/instances/{instance_id}/server-operations
```

Returns Server Operations belonging to the Game Instance.

### Optional Query Parameters

```text
status
capability
limit
before
```

Initial rules:

- `limit` should have a safe maximum.
- `before` may be used for cursor-style pagination.
- Unsupported filter values should return a validation error.

### Successful Response

```json
{
    "server_operations": [
        {
            "id": "operation-id",
            "instance_id": "instance-id",
            "capability": "instance.restart",
            "status": "completed",
            "current_stage": "completed",
            "requested_by": {
                "id": "user-id",
                "display_name": "Chad"
            },
            "requested_at": "2026-07-10T15:35:00Z",
            "started_at": "2026-07-10T15:35:02Z",
            "completed_at": "2026-07-10T15:37:14Z",
            "duration_seconds": 132,
            "result_message": "Genesis restarted and passed all required health checks."
        }
    ]
}
```

### Processing Requirements

- Authenticate the user.
- Verify access to the Game Instance's Community.
- Return only Server Operations for the requested Game Instance.
- Order results from newest to oldest unless otherwise documented.

---

## Get Server Operation

```text
GET /api/v1/server-operations/{operation_id}
```

Returns the full state of one Server Operation.

### Successful Response

```json
{
    "server_operation": {
        "id": "operation-id",
        "instance_id": "instance-id",
        "capability": "instance.restart",
        "status": "verifying",
        "current_stage": "broadcasting_check",
        "requested_by": {
            "id": "user-id",
            "display_name": "Chad"
        },
        "requested_at": "2026-07-10T15:35:00Z",
        "started_at": "2026-07-10T15:35:02Z",
        "completed_at": null,
        "duration_seconds": null,
        "result_message": null,
        "checks": [
            {
                "id": "check-id-1",
                "name": "process_stopped",
                "status": "passed",
                "started_at": "2026-07-10T15:35:04Z",
                "completed_at": "2026-07-10T15:35:10Z",
                "result_message": "The expected ARK process stopped.",
                "sort_order": 1
            },
            {
                "id": "check-id-2",
                "name": "process_running",
                "status": "passed",
                "started_at": "2026-07-10T15:35:20Z",
                "completed_at": "2026-07-10T15:35:27Z",
                "result_message": "The expected ARK process started.",
                "sort_order": 2
            },
            {
                "id": "check-id-3",
                "name": "port_reachable",
                "status": "passed",
                "started_at": "2026-07-10T15:35:28Z",
                "completed_at": "2026-07-10T15:35:31Z",
                "result_message": "The expected network port responded.",
                "sort_order": 3
            },
            {
                "id": "check-id-4",
                "name": "broadcasting",
                "status": "running",
                "started_at": "2026-07-10T15:35:32Z",
                "completed_at": null,
                "result_message": null,
                "sort_order": 4
            }
        ]
    }
}
```

### Processing Requirements

- Authenticate the user.
- Resolve the target Game Instance and Community.
- Verify Community access.
- Return ordered stage and health-check records.
- Do not expose raw command lines, credentials, or secret configuration.

---

# Server Operation Lifecycle

Initial lifecycle statuses:

- `requested`
- `queued`
- `executing`
- `verifying`
- `completed`
- `failed`
- `cancelled`

Detailed lifecycle behavior is defined in:

```text
docs/server-operation-lifecycle.md
```

### Status Rules

- `requested` means the record exists but execution has not begun.
- `queued` means the operation is waiting to execute.
- `executing` means the requested Capability is running.
- `verifying` means execution has finished and the result is being checked.
- `completed` means every required verification passed.
- `failed` means execution or verification failed.
- `cancelled` means the operation ended before successful completion.

A command finishing with exit code zero does not by itself justify `completed`.

---

# Server Operation Checks

Checks represent deterministic execution stages or verification results associated with a Server Operation.

Initial check statuses:

- `pending`
- `running`
- `passed`
- `failed`
- `skipped`

### Check Rules

- Checks must be returned in `sort_order`.
- A failed required check should cause the Server Operation to fail.
- A skipped check must include a reason when the reason is known.
- An unavailable or unimplemented check must not be recorded as passed.
- Public result messages should be useful without exposing infrastructure secrets.

---

# Conflicting Operations

The API should prevent operations that could interfere with each other.

Examples:

- A second restart while a restart is already active.
- A save while the Instance is stopping.
- A backup during a conflicting restore.

When a conflict exists, return:

```json
{
    "error": {
        "code": "OPERATION_ALREADY_RUNNING",
        "message": "A conflicting Server Operation is already active for this Instance."
    }
}
```

The first vertical slice only needs conflict prevention where the implemented Capability requires it.

---

# Failed Server Operation Example

```json
{
    "server_operation": {
        "id": "operation-id",
        "instance_id": "instance-id",
        "capability": "instance.restart",
        "status": "failed",
        "current_stage": "broadcasting_check",
        "requested_at": "2026-07-10T15:35:00Z",
        "started_at": "2026-07-10T15:35:02Z",
        "completed_at": "2026-07-10T15:40:00Z",
        "duration_seconds": 298,
        "result_message": "The ARK process was running, but the server did not become queryable before the verification timeout.",
        "checks": [
            {
                "name": "process_stopped",
                "status": "passed"
            },
            {
                "name": "process_running",
                "status": "passed"
            },
            {
                "name": "port_reachable",
                "status": "passed"
            },
            {
                "name": "broadcasting",
                "status": "failed",
                "result_message": "The game query did not succeed before timeout."
            }
        ]
    }
}
```

Failure responses should describe the failed outcome honestly.

They must not claim that the Instance is ready when required verification did not pass.

---

# Engineering (Reserved)

The Engineering Tracker is not part of the initial vertical slice.

The following routes are reserved for future implementation.

## List Issues

```text
GET /api/v1/issues
```

Optional filters may include:

- type
- status
- priority
- implementation_agent
- reviewer

---

## Create Issue

```text
POST /api/v1/issues
```

Example

```json
{
    "type": "improvement",
    "title": "Community Activity Feed",
    "description": "Display recent Community and Hosting activity.",
    "priority": "high"
}
```

---

## Get Issue

```text
GET /api/v1/issues/{issue_id}
```

---

## Update Issue

```text
PATCH /api/v1/issues/{issue_id}
```

The Engineering API is reserved for future implementation.

---

# Error Format

All API errors should follow a consistent structure.

```json
{
    "error": {
        "code": "FORBIDDEN",
        "message": "You do not have permission to perform this operation."
    }
}
```

Initial error codes:

- `UNAUTHENTICATED`
- `INVALID_CREDENTIALS`
- `FORBIDDEN`
- `NOT_FOUND`
- `VALIDATION_ERROR`
- `CONFLICT`
- `CAPABILITY_UNAVAILABLE`
- `CONFIRMATION_REQUIRED`
- `OPERATION_ALREADY_RUNNING`
- `INTERNAL_ERROR`
- `EMAIL_ALREADY_REGISTERED`
- `PASSWORD_MISMATCH`

### Error Rules

- Error messages should be useful.
- Errors should not expose passwords.
- Errors should not expose command strings.
- Errors should not expose stack traces.
- Errors should not expose server credentials.
- Errors should not expose filesystem paths.
- Errors should not reveal inaccessible resources unless intentionally permitted.

---

# Authorization

Authentication identifies the User.

Authorization determines what the User is permitted to do.

Authorization is based upon:

```text
User

↓

Community Membership

↓

Community Role

↓

Capability Permission
```

Detailed authorization rules are defined in:

```text
docs/authentication.md
```

Every protected endpoint must perform authorization on the server.

Client-side controls improve usability.

They are not security.

---

# Current Supported API

This document defines every API endpoint that is currently approved for implementation within TWE.

Individual Vertical Slice documents specify which subset of these endpoints is required to complete a particular user journey.

Implementations should expose only documented endpoints.

New endpoints require an approved design change.

---

## Authentication

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

---

## Communities

```text
GET /api/v1/communities
GET /api/v1/communities/{community_id}
GET /api/v1/communities/{community_id}/game-servers
```

---

## Game Servers

```text
GET /api/v1/game-servers/{game_server_id}
GET /api/v1/game-servers/{game_server_id}/instances
```

---

## Game Instances

```text
GET /api/v1/instances/{instance_id}
GET /api/v1/instances/{instance_id}
GET /api/v1/instances/{instance_id}/health
GET /api/v1/instances/{instance_id}/capabilities
```

---

## Server Operations

```text
POST /api/v1/instances/{instance_id}/server-operations
GET  /api/v1/instances/{instance_id}/server-operations
GET  /api/v1/server-operations/{operation_id}
```

---

## Engineering (Reserved)

```text
GET  /api/v1/issues
POST /api/v1/issues
GET  /api/v1/issues/{issue_id}
PATCH /api/v1/issues/{issue_id}
```

These endpoints are approved for future implementation but are not required by the current vertical slices.

---

# Vertical Slice Responsibility

The API Design document defines the complete platform API.

Each Vertical Slice document identifies the subset of endpoints required to implement its specific user journey.

Examples:

- `docs/vertical-slices/citw-genesis-v1.md`
- `docs/vertical-slices/visitor-to-user-v1.md`

An implementation should not introduce undocumented endpoints or omit required endpoints for the active Vertical Slice.

Additional endpoints require an approved architecture change before implementation.

---

# API Design Rules

The API should expose business concepts rather than implementation details.

Examples:

Expose:

- Community
- Game Server
- Game Instance
- Capability
- Server Operation

Do not expose:

- shell commands
- script filenames
- operating-system process identifiers
- PostgreSQL credentials
- SSH credentials
- filesystem layouts
- implementation-specific infrastructure

The API contract should remain stable even if the underlying implementation changes.

---

# Out of Scope

This document does not define:

- PostgreSQL schema
- migration implementation
- authentication internals
- UI layout
- CSS styling
- Management Adapter implementation
- deterministic workflow implementation
- deployment
- infrastructure configuration
- Engineering Tracker implementation
- future roadmap items

Refer to the appropriate engineering documents for those concerns.

---

# Related Documentation

This document should be interpreted together with:

```text
docs/glossary.md
docs/database-schema.md
docs/authentication.md
docs/server-operation-lifecycle.md
docs/codex-guidelines.md
docs/vertical-slices/citw-genesis-v1.md
```

When conflicts exist, the documentation precedence defined in:

```text
docs/README.md
```

is authoritative.

Implementation should pause until documentation conflicts have been resolved.

---

# Final Principle

The API exists to expose the TWE business model.

It should provide a stable, secure, and predictable interface for clients while hiding infrastructure details and implementation complexity.

Every endpoint should strengthen the documented architecture rather than redefine it.
