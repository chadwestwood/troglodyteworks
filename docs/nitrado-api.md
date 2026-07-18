# Nitrado API Research

## Purpose

This document summarizes Nitrado's public programming interface, NitrAPI, and evaluates its use as a TWE Management Adapter.

Research was verified against Nitrado-owned documentation on July 13, 2026. The official endpoint catalog reported a generation timestamp of July 9, 2026. The catalog is live documentation and must be rechecked before implementation.

## Executive Summary

NitrAPI is Nitrado's REST API for managing customer services. It is the correct direct integration surface for Nitrado-hosted Game Instances. Its game-server routes cover service discovery, status and details, start/restart/stop operations, settings, statistics, backups, file management, scheduled tasks, game installation, and player administration.

For TWE, the central design is:

```text
Discord / Web UI
        |
        v
TWE authorization and Server Operation
        |
        v
Nitrado Management Adapter
        |
        v
https://api.nitrado.net
```

Trog must never call Nitrado directly. Trog requests a TWE Server Operation; the backend authorizes it, invokes the adapter, records provider correlation data, polls or verifies the result, and writes the audit trail defined by `docs/server-operation-lifecycle.md`.

## Protocol and Response Model

The official base URL is:

```text
https://api.nitrado.net
```

The published documentation labels the contract `1.0.0`. Routes generally use JSON and return envelopes such as:

```json
{
  "status": "success",
  "message": "Optional human-readable result",
  "data": {}
}
```

Clients should use the HTTP status and structured fields, not compare human-readable messages. Error examples commonly include:

- `401` for an invalid or expired access token
- `429` for rate limiting
- `503` for maintenance

The public documentation does not publish a universal numeric quota. The adapter must treat limits as dynamic and implement bounded retry behavior rather than hard-code an assumed request rate.

## Authentication and Authorization

NitrAPI uses OAuth 2.0 bearer tokens.

Authenticated requests should send:

```http
Authorization: Bearer <access-token>
```

The documentation also notes token query parameters on some routes. TWE should always use the authorization header because URLs are more likely to be retained in browser history, proxy logs, analytics, and monitoring systems.

### Authorization-code flow

The current published endpoints are:

| Purpose | Endpoint |
| --- | --- |
| User authorization | `GET /oauth/v2/auth` |
| Code or refresh exchange | `POST /oauth/v2/token` |
| Token identity/details | `GET /token` |
| Token revocation | `DELETE /oauth/v2/token` |

Nitrado documents only the explicit authorization-code response type for user authorization. A secure TWE flow must:

1. register a Nitrado OAuth client and exact callback URI
2. generate and store a cryptographically random `state`
3. redirect to `/oauth/v2/auth` with `client_id`, `redirect_uri`, requested `scope`, `response_type=code`, and `state`
4. reject a callback whose `state` does not match
5. exchange the code server-side using the client credentials
6. encrypt returned tokens at rest
7. fetch `/token` and bind the immutable Nitrado user ID to the integration record

The official documentation says ordinary access tokens are valid for one day and refresh tokens for one month. A refresh invalidates and replaces both the prior access token and refresh token. Refresh storage therefore needs the same atomic rotation behavior as Beacon.

### Long-life tokens and sub-tokens

Nitrado also documents:

- `POST /token/long_life_token` for automation tokens valid for many years
- `GET /token/long_life_token` and `DELETE /token/long_life_token/{id}` for lifecycle management
- `POST /token/sub` to derive a shorter-lived or reduced-scope token, optionally restricted to one `service_id`

For a multi-user TWE product, the normal OAuth flow is preferable. A user-pasted long-life token creates difficult rotation, revocation, and support risks. If a deployment initially requires long-life tokens, TWE should immediately derive the narrowest service-bound sub-token available and never expose either token back to Discord.

### Scopes and roles

OAuth scopes such as `user_info`, `service`, and `service_order` govern broad token access. Individual routes also document service roles such as:

- `ROLE_OWNER`
- `ROLE_WEBINTERFACE_GENERAL_CONTROL`
- `ROLE_WEBINTERFACE_SETTINGS_READ`
- `ROLE_WEBINTERFACE_SETTINGS_WRITE`
- `ROLE_WEBINTERFACE_BACKUPS_READ`
- `ROLE_WEBINTERFACE_BACKUPS_WRITE`
- `ROLE_WEBINTERFACE_FILEBROWSER_READ`
- `ROLE_WEBINTERFACE_FILEBROWSER_WRITE`
- `ROLE_WEBINTERFACE_LOGS_READ`
- scheduled-restart read/write roles

These provider roles are an additional constraint, not TWE authorization. TWE must still resolve Community Membership and Capability Grants before sending a provider request.

## Service and Game-Server Model

Nitrado identifies a purchased product as a **service**. A game-server service is addressed by `service_id` and has game-server-specific subresources.

TWE should persist mappings similar to:

| TWE field | Nitrado value |
| --- | --- |
| Management Adapter | `nitrado` |
| Provider account | Immutable Nitrado user ID from `/token` |
| Provider service ID | Nitrado `service_id` |
| Game Instance status | Normalized from service/game-server details |
| Provider game key | Nitrado game identifier |

Provider state strings must be normalized into TWE's stable state model while retaining the original payload for diagnostics. A Nitrado service does not automatically equal a TWE Game Server; it is provider infrastructure attached to the relevant Game Instance or hosting record.

## Core Endpoint Families

### Discovery and details

| Method and route | Use |
| --- | --- |
| `GET /services` | List services available to the token. |
| `GET /services/{id}` | Fetch service-level details. |
| `GET /services/{id}/gameservers` | Fetch game-server status and details. |
| `GET /game/list` | Public game catalog. |
| `GET /game/list_auth` | Authenticated game catalog. |

Service discovery should happen during account connection and periodic reconciliation. Administrative commands should use the stored, verified service mapping rather than accept a raw service ID from Discord.

### Lifecycle control

| Method and route | Use |
| --- | --- |
| `POST /services/{id}/gameservers/games/start` | Start the selected game. |
| `POST /services/{id}/gameservers/restart` | Restart the game server. |
| `POST /services/{id}/gameservers/stop` | Stop the game server. |

These calls can represent asynchronous work. A successful API response means Nitrado accepted or initiated an action; it does not prove that players can connect. The adapter must verify completion by polling game-server details and, where applicable, performing a query or RCON readiness check.

For restart operations, TWE should:

1. authorize and create the Server Operation
2. record the pre-operation provider state
3. send exactly one restart request with a stable internal operation ID
4. poll with bounded exponential backoff
5. require a meaningful transition and eventual ready state
6. distinguish accepted, in progress, succeeded, failed, and timed out
7. avoid automatically issuing a second restart after an ambiguous timeout

### Settings and configuration

The catalog includes:

- `GET /services/{id}/gameservers/settings`
- `POST /services/{id}/gameservers/settings`
- `DELETE /services/{id}/gameservers/settings` to reset settings
- defaults and named setting-set routes
- restore of a setting set
- game-specific routes for supported titles

Settings are provider- and game-specific. They should be translated through a game/provider schema layer. TWE must not expose arbitrary setting keys as universally safe.

Before a write:

- fetch current settings or maintain a verified snapshot
- validate key, type, range, and game compatibility
- compute and present the intended change
- retain rollback material where the provider supports it
- verify that the effective settings match after any required restart

### Backups

The documented routes include:

- `GET /services/{id}/gameservers/backups`
- database and game-server backup creation routes
- restore-possibility checks
- backup restore operations

Backup restore is destructive to current world state and must be a high-risk Server Operation with explicit confirmation, a chosen backup identifier, a pre-restore backup when possible, and post-restore validation. Backup timestamps and time zones must be normalized before display.

### Files and FTP

The file-server API covers bookmarks, listing, stat, size, seek, download, upload, copy, move, directory creation, and deletion. There is also an FTP password route.

This surface is powerful and dangerous. File access should be isolated behind capabilities narrower than general server administration. Enforce canonical provider paths, deny traversal, restrict allowed roots and extensions per game, cap upload/download size, and never return provider credentials to a Discord channel.

For configuration deployment, prefer a provider setting endpoint when it represents the required setting. Use file writes only where the supported game requires direct file management.

### Players and access lists

NitrAPI publishes routes for players and admin, ban, and whitelist lists, including player actions. These enable moderation workflows but should be added only after TWE defines stable player identifiers, target confirmation, appeal/audit expectations, and separate capabilities for read, kick, ban, unban, whitelist, and administrator changes.

Display names are not safe identifiers. Persist and act on the provider/game identifier returned by the API.

### Statistics, logs, and scheduled tasks

Relevant routes include:

- game-server statistics
- service logs
- task listing, available task types, create, update, and delete

Scheduled provider tasks can conflict with TWE scheduling. TWE must either designate Nitrado as the source of truth and reconcile tasks, or manage schedules itself and clearly identify externally created tasks. Two uncoordinated schedulers can cause duplicate restarts.

## Reliability and State Management

The adapter should implement:

- short connect and read timeouts
- bounded exponential backoff with jitter for safe reads and explicit transient failures
- no blind retry of non-idempotent writes after an unknown response
- token refresh under a per-connection lock
- concurrency control per provider service
- circuit breaking during Nitrado maintenance
- redaction of tokens, credentials, file contents, and sensitive response fields
- correlation between every provider request and one TWE Server Operation

Nitrado routes sometimes require a particular service status. The adapter should treat `409`-style state conflicts or documented precondition failures as operational outcomes, not generic crashes, and return a useful normalized reason.

## Recommended Initial TWE Slice

### Beta long-life-token discovery decision

Slice 2B validates a user-generated long-life token by calling `GET /services`
directly with an Authorization bearer header. The live official endpoint catalog
was rechecked on July 17, 2026. Because validation and discovery use only this
endpoint, the beta requires only the `service` scope. It does not call `GET /token`
or request `user_info`.

The service-list response supplies the service ID, type, status, display details,
game title, slots, address, location, and suspension date needed here. Slice 2B
avoids `GET /services/{id}/gameservers` because the official example includes
credential fields outside this slice.

Implement the smallest useful adapter in this order:

1. OAuth account connection and revocation.
2. Service discovery and explicit administrator mapping to a TWE Game Instance.
3. Read-only status and basic server details.
4. Restart through the full Server Operation lifecycle.
5. Stop and start with distinct capabilities and confirmation policy.
6. Backup listing and creation.
7. Settings reads, followed by validated writes.
8. Restore, file management, and player moderation only after dedicated safety contracts.

Recommended capability mapping:

| TWE capability | Nitrado action |
| --- | --- |
| `instance.status.read` | Read game-server details. |
| `instance.restart.execute` | Request restart and verify readiness. |
| Future `instance.stop.execute` | Stop and verify stopped state. |
| Future `instance.start.execute` | Start and verify ready state. |
| Future backup capabilities | List, create, or restore backups separately. |

## Documentation Gaps and Required Validation

- Nitrado does not publish a fixed universal rate-limit quota in the reviewed reference.
- Some endpoint pages contain old example payloads even though the live catalog is recently generated.
- Exact game support and game-specific setting keys vary by service and must be discovered using a real test service.
- No authenticated calls or destructive operations were performed because no Nitrado test account, token, or service was provided.
- Async transition timing, idempotency behavior, and error payloads must be measured in a sandbox service before production use.

## Official Sources

- [Nitrado developer documentation](https://developers.nitrado.net/)
- [NitrAPI endpoint reference](https://doc.nitrado.net/)
- [Nitrado overview of NitrAPI](https://server.nitrado.net/usa/news2/view/the-nitrapi-nitrados-programming-interface-for-ordering-managing-and-controlling-services/)
- [Beacon's documented Nitrado authorization workflow](https://help.usebeacon.app/servers/importing/)
