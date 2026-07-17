# Vertical Slice: Community Owner Connects a Nitrado Service V1

## Status

Blocked at the secret-persistence security gate on July 17, 2026.

The provider-neutral foundation can represent a Nitrado Provider Connection,
Provider Resource, and Game Server binding without a material schema redesign.
It cannot yet store a Nitrado long-life token safely. Migration `0011` permits an
external secret reference or an authenticated encrypted payload envelope, but the
repository contains no approved authenticated-encryption implementation, external
secret manager integration, database-external key configuration, or key-rotation
policy.

Per this slice's stop conditions, no real token may be accepted or persisted until
that design is approved and implemented. Plaintext, reversible obfuscation,
base64, and hashing-only substitutes are prohibited.

## Implemented Blocking Boundary

`ProviderSecretStorage` defines provider-neutral store, replace, read, and delete
operations. The configured factory returns `UnavailableProviderSecretStorage`.
Every operation fails with the fixed
`PROVIDER_SECRET_STORAGE_UNAVAILABLE` error and does not access the database,
provider, or supplied credential. The error contains no credential material.

This boundary is not an encryption implementation and must not be presented as
one. It exists so future connection code cannot silently fall back to unsafe
storage.

## Intended Purpose and User Journey

After the security gate is resolved, this slice will allow a signed-in Community
Owner to choose **Connect Hosting**, select Nitrado, create and submit a revocable
long-life token, choose one discovered ARK: Survival Ascended service, and bind it
to a Community Game Server. The connected summary will remain visible after
refresh. No part of that browser journey is implemented while secure persistence
is blocked.

OAuth is explicitly deferred. The beta design uses user-generated, revocable
Nitrado long-life tokens.

## Security Model

The approved storage implementation must use either:

- an external secret manager represented by `external_reference`; or
- authenticated encryption represented by `encrypted_payload`, with required
  envelope metadata and encryption keys held outside PostgreSQL.

It must support safe replacement and deletion, never expose tokens through APIs or
representations, and never place token values or fragments in logs, exceptions,
audit events, URLs, cookies, frontend storage, or persisted provider metadata.
State-changing browser routes must follow the existing CSRF mechanism and all
connection actions must require the exact Community `owner` role.

## Nitrado Token Scope Decision

No scope has been hard-coded. The intended minimum is `service`; `user_info` may be
added only if current official Nitrado validation or discovery endpoints require
it. `rootserver`, `ssh_keys`, `user_edit`, and `service_order` are outside this
slice and must not be requested.

Current official endpoint and scope behavior must be revalidated after secret
storage is approved and immediately before adapter implementation. The existing
research document is not a substitute for that implementation-time validation.

## Deferred Route Contracts

No Slice 2 routes are registered. The proposed `/api/v1` route family remains:

- create or replace a Community Nitrado hosting connection;
- discover resources for that connection;
- list its safe normalized resources;
- explicitly select a resource and Game Server;
- explicitly disconnect the connection.

Stable requests, responses, error mappings, and CSRF behavior must be documented
when implemented. Secret records and token values must never be API resources.

## Deferred Provider Adapter and Normalization

No Nitrado HTTP client or provider adapter is registered. Once unblocked, all
Nitrado-specific HTTP behavior must remain behind the unified provider registry,
use explicit timeouts, and mock HTTP in automated tests. Only ARK: Survival
Ascended may normalize to `ark_survival_ascended`. The Nitrado service ID—not an IP
address or port—will be the external resource identifier. Only useful non-secret
metadata may be retained, and raw provider responses will not be persisted.

## Database Effects and Audit Events

This blocked implementation adds no migration and writes no Provider Connection,
Provider Connection Secret, Provider Resource, Game Server binding, or audit
event. Migration `0011_provider_foundation.sql` remains unchanged.

When the slice proceeds, remote calls must occur outside database transactions;
local connection, discovery, selection, binding, and disconnection mutations must
be transactional and idempotent. Audit events will record connection creation,
token replacement, completed discovery, selection, and disconnection without any
secret material.

## Error Handling

The only new error is `PROVIDER_SECRET_STORAGE_UNAVAILABLE`. It is deterministic,
contains no supplied credential, and is raised for store, replace, read, and delete
while no approved backend exists. Provider authentication, scope, rate-limit,
timeout, malformed-response, availability, unsupported-game, disappearance, and
binding-conflict errors remain deferred with the adapter and routes.

## Test Coverage

The blocking tests prove that the default backend is unavailable, every secret
operation refuses to proceed, and the failure text and representation do not
contain the supplied token. No live Nitrado account or token is used.

The full Slice 2 test matrix remains required after the security gate is resolved,
including Owner authorization, non-owner denial, CSRF, mocked Nitrado outcomes,
idempotency, binding constraints, transaction boundaries, audit redaction,
frontend behavior, and existing provider/Discord/operation regressions.

## Live Validation Procedure

No live validation is permitted while this slice is blocked. After approval and
implementation of secure persistence, a separately reviewed read-only plan may use
a development-only token with verified minimum scopes to validate identity only if
needed, list services, identify one ARK: Survival Ascended service, and compare
normalized non-secret fields with the dashboard. The token must never enter Codex,
source control, fixtures, shell history, logs, screenshots, or documentation.

## Known Limitations

- There is no approved secret backend or database-external key management.
- No Nitrado token scope has been implementation-validated.
- There is no Nitrado client, adapter, registry entry, API, UI, persistence, audit
  behavior, discovery, selection, binding, replacement, revocation, or disconnect
  workflow.
- Existing self-hosted Genesis and Pterodactyl behavior is intentionally unchanged.

## Slice 3 Prerequisites

Slice 2 must first be fully unblocked, implemented, and verified. At minimum this
requires approval of the secret backend and key lifecycle, current official
Nitrado endpoint/scope validation, complete mocked Slice 2 coverage, migration and
transaction validation, frontend verification at required viewports, and a
security review. This work does not authorize or begin Slice 3.
