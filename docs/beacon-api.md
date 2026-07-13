# Beacon API Research

## Purpose

This document summarizes Beacon's public API and evaluates where it fits in Troglodyte Works Experience (TWE).

Research was verified against Beacon's official documentation on July 13, 2026. Vendor APIs change independently of this repository, so endpoint details must be rechecked before implementation.

## Executive Summary

Beacon is a game-server configuration and community-data platform. Its current API, version 4, exposes Beacon users, projects, project invitations, reusable templates, game metadata, and Beacon Sentinel data through a JSON REST interface.

For TWE, Beacon is most useful for:

- reading game metadata such as ARK blueprints, creatures, maps, loot drops, spawn points, and configuration options
- exchanging or synchronizing Beacon projects and templates
- integrating with Beacon Sentinel's player, group, ban, script, log, service, and tribe records
- allowing a TWE user to authorize access to their Beacon account

Beacon is not documented as a general-purpose hosting-provider control API. It should not replace TWE's Management Adapter or the Nitrado API for starting, stopping, restarting, backing up, or directly configuring a hosted Game Instance. Beacon itself can deploy configuration to supported hosts such as Nitrado, but that product workflow is distinct from the public Beacon v4 resource API.

## Product Boundaries

Beacon has three related surfaces that should not be confused:

1. **Beacon application:** creates and deploys game configuration projects.
2. **Beacon API v4:** exposes Beacon-owned resources, game data, projects, sessions, users, and Sentinel records.
3. **Beacon Sentinel:** an ARK-focused monitoring and automation product whose data is represented by many v4 API classes.

The older v1 documentation describes documents, engrams, mods, users, RSA-signed mutations, and a mod engram pull API. That is a legacy API generation. New integration design should target v4 unless a required capability exists only in v1 and Beacon confirms that v1 remains supported.

## Protocol and Resource Model

The service base is:

```text
https://api.usebeacon.app
```

Version 4 resources use paths under `/v4`. The API uses JSON and a predictable class/instance model:

- a **class path**, such as `/v4/projects`, addresses a collection
- an **instance path**, such as `/v4/projects/{projectId}`, addresses one object
- `GET` on a class path lists objects
- `GET` on an instance path fetches one object
- `POST` on a class path creates or bulk-updates objects
- `PUT` replaces or creates an instance
- `PATCH` partially updates an existing instance
- `DELETE` removes one or more instances
- `HEAD` is supported only by classes that list it explicitly

Every class has its own supported methods, identifier, filterable properties, and sortable properties. A generic REST client must therefore use the class documentation rather than assume every method is accepted for every resource.

### Listing and pagination

Collection results are always paginated. Common query parameters are:

| Parameter | Meaning |
| --- | --- |
| `page` | One-based page number; defaults to `1`. |
| `pageSize` | Number of results; defaults to and is capped at `250`. |
| `sortedColumn` | A class-specific sortable property. |
| `sortDirection` | `ascending` or `descending`. |

The standard collection envelope is:

```json
{
  "totalResults": 1,
  "pageSize": 250,
  "pages": 1,
  "page": 1,
  "results": []
}
```

Filters are class-specific. Their matching behavior can differ; for example, one string property may use a case-insensitive contains match while another property may require an exact match.

### Create and update behavior

A `POST` to a class path accepts one object or an array. Beacon determines create versus update by the presence and existence of the class identifier. Successful responses separate results into `created` and `updated` arrays.

This is convenient for synchronization, but a caller must avoid treating `POST` as create-only. Supplying an existing identifier can mutate existing data.

## Authentication

Beacon API v4 uses OAuth 2.1 with PKCE. The published endpoints are:

| Purpose | Endpoint |
| --- | --- |
| Authorization and token exchange | `https://api.usebeacon.app/v4/login` |
| Device authorization | `https://api.usebeacon.app/v4/device` |
| Current session | `https://api.usebeacon.app/v4/session` |

### Browser authorization-code flow

1. Register an application and callback URL with Beacon.
2. Generate cryptographically random `state` and `code_verifier` values.
3. Derive `code_challenge = BASE64URL(SHA256(code_verifier))`.
4. Redirect the user to `/v4/login` with `client_id`, space-separated `scope`, exact `redirect_uri`, `state`, `response_type=code`, `code_challenge`, and `code_challenge_method=S256`.
5. On callback, compare the returned `state` before using the authorization code.
6. Exchange the code at `/v4/login` with `grant_type=authorization_code`, the original redirect URI, and raw verifier.
7. Store the returned access and refresh tokens encrypted at rest.

Confidential clients include their client secret during token exchange. Public clients omit it; they still use PKCE.

### Device flow

Beacon also documents a device flow for environments where opening a browser is impractical, explicitly including Discord bots as an example. A client requests a device code from `/v4/device`, directs the user to the verification URL, and polls `/v4/login` with `grant_type=device_code` and the verifier.

For Trog, a normal browser deep link tied to a short-lived TWE linking transaction is likely easier to audit than device polling. The device flow remains useful for command-line or appliance-style clients.

### Token use and lifecycle

Server-side calls use:

```http
Authorization: Bearer <access-token>
```

Beacon documents `X-Beacon-Token: <access-token>` for browser requests because its CORS policy does not expose the standard authorization header in that context.

At the time of the official documentation:

- access tokens expire after approximately one hour
- refresh tokens expire after approximately 30 days
- refresh replaces both the access token and refresh token
- refresh requests must repeat the originally requested scope set
- `DELETE /v4/session` revokes the current session

Token rotation must be atomic. If TWE stores the new access token but fails to replace the rotated refresh token, the integration can lose access and require user authorization again.

### Published scopes

| Scope | Capability |
| --- | --- |
| `common` | Always included; common features such as game information. |
| `users:read` | Read the authenticated user and other user information. |
| `users:update` | Edit the user. |
| `users.private_key:read` | Fetch the private key needed for encrypted project portions and cloud files. |
| `sentinel:read` | Read the user's Sentinel data. |
| `sentinel:write` | Modify Sentinel data, including servers, groups, bans, and scripts. |

`users.private_key:read` is exceptionally sensitive. TWE should not request it unless encrypted Beacon project content is an approved requirement and a separate key-handling design has been reviewed.

## Major Resource Families

### Game metadata

Beacon documents rich class models for:

- ARK: Survival Ascended
- ARK: Survival Evolved
- Palworld configuration options and variables
- cross-game content packs and discovery results

ARK resources include blueprints, colors, color sets, configuration options, creatures, engrams, events, game variables, loot drops, maps, and spawn points. These can support a Game Specialist experience and configuration validation without TWE maintaining a duplicate hand-curated catalog.

### Projects and collaboration

`Project` uses class path `/v4/projects` and identifier `projectId`. The current class reference lists `POST`, `GET`, and `DELETE` on the collection and `GET`, `DELETE`, and `HEAD` on instances.

Related classes include:

- `ProjectInvite`
- `Template`
- `TemplateSelector`
- `User`
- `Session`

The published `Project` class page currently provides very little property detail. Before building synchronization, TWE should capture real authorized responses in a non-production account and confirm project payload semantics, encryption, ownership, conflict behavior, and file-size limits.

### Sentinel

Sentinel is the broadest operational data family in Beacon v4. Its classes cover:

- services, service users, service bans, and service scripts
- players, identifiers, sessions, name changes, and notes
- characters, dinos, and tribes
- groups, group users, bans, services, scripts, and buckets
- log messages, game commands, scripts, and script webhooks

This data may complement TWE's Game Instance monitoring. It should remain an external source behind an adapter; Beacon-specific object names must not leak into the universal TWE Game Server and Game Instance model.

## Errors, Retries, and Security

Beacon documents conventional success statuses (`200`, `201`, and `204`) and these important errors:

| Status | Meaning and handling |
| --- | --- |
| `400` | Invalid request; do not retry unchanged. |
| `401` | Missing authentication; refresh or reauthorize. |
| `403` | Token is invalid or lacks authority; do not retry unchanged. |
| `404` | Missing object, or deliberately hidden unauthorized object. |
| `412` | A required condition is not satisfied. |
| `429` | Rate limit exceeded; delay according to response information. |
| `500`, `502`, `503`, `504` | Transient server or edge failures; use bounded backoff. |

Security requirements for a TWE integration:

- request the minimum OAuth scopes
- validate OAuth `state` and PKCE on every authorization
- encrypt access tokens, refresh tokens, client secrets, and any private key material at rest
- never place tokens in logs, Discord messages, URLs controlled by TWE, or source control
- revoke the Beacon session when a user disconnects the integration
- preserve vendor identifiers separately from TWE identifiers
- audit every TWE action that causes a Beacon mutation
- make retries idempotent and bounded, especially for bulk mutations

## Recommended TWE Integration

Implement Beacon as an optional external integration with separate capabilities:

1. **Metadata reader:** cache public/common game metadata with source timestamps.
2. **Project connector:** use user OAuth for explicitly approved project workflows.
3. **Sentinel connector:** use `sentinel:read` first; add writes only with a concrete administrative workflow and audit model.

Do not route Game Instance start, stop, restart, backup, or provider file-management operations through Beacon unless Beacon publishes and supports a specific contract for them. Those operations belong to the hosting provider's Management Adapter, such as Nitrado.

## Documentation Gaps and Required Validation

- The v4 class index is broad, but some individual class pages expose sparse property or example data.
- The official v4 pages reviewed do not publish a complete rate-limit algorithm or quota table.
- Public documentation does not establish Beacon v4 as a generic remote server-control interface.
- Legacy v1 and current v4 authentication and object models differ substantially.
- Real project and Sentinel payloads were not exercised because no user credentials or test account were provided.

## Official Sources

- [Beacon API v4 reference](https://help.usebeacon.app/api/v4/)
- [Beacon API v4 authentication](https://help.usebeacon.app/api/v4/authentication/)
- [Beacon API v4 REST guide](https://help.usebeacon.app/api/v4/rest/)
- [Beacon Project class](https://help.usebeacon.app/api/v4/classes/project/)
- [Beacon Session class](https://help.usebeacon.app/api/v4/classes/session/)
- [Beacon Sentinel classes](https://help.usebeacon.app/api/v4/classes/sentinel/)
- [Beacon legacy v1 API](https://usebeacon.app/docs/api/v1/)
- [Beacon and Nitrado import workflow](https://help.usebeacon.app/servers/importing/)

