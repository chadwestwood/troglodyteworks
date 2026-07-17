# Vertical Slice: Community Owner Connects a Nitrado Service V1

## Status

Secret-persistence prerequisite implemented on July 17, 2026. The broader Slice 2
Nitrado journey remains deferred.

The provider-neutral foundation can represent a Nitrado Provider Connection,
Provider Resource, and Game Server binding without a material schema redesign.
Migration `0011` supports authenticated encrypted payload envelopes. The approved
implementation now protects those envelopes with AES-256-GCM and versioned keys
provided outside PostgreSQL. Plaintext, reversible obfuscation, base64, and
hashing-only substitutes remain prohibited.

## Implemented Secret-Storage Boundary

`ProviderSecretStorage` defines provider-neutral store, replace, read, delete, and
key-rotation operations. When a complete keyring is configured, the application
uses `AuthenticatedProviderSecretStorage`. Without one, it returns
`UnavailableProviderSecretStorage`; every operation fails with the fixed
`PROVIDER_SECRET_STORAGE_UNAVAILABLE` error.

The authenticated implementation stores only ciphertext, a fresh 12-byte nonce,
and key version. The Provider Connection ID and key version are authenticated as
associated data. Authentication failure produces a fixed error without returning
plaintext. Replacement and explicit re-encryption update the complete envelope
transactionally. Rotation locks the row so it cannot overwrite a concurrent token
replacement.

## Intended Purpose and User Journey

The remaining slice will allow a signed-in Community Owner to choose **Connect
Hosting**, select Nitrado, create and submit a revocable
long-life token, choose one discovered ARK: Survival Ascended service, and bind it
to a Community Game Server. The connected summary will remain visible after
refresh. That browser journey is not part of the secret-storage implementation.

OAuth is explicitly deferred. The beta design uses user-generated, revocable
Nitrado long-life tokens.

## Security Model

Provider secrets may use either:

- an external secret manager represented by `external_reference`; or
- AES-256-GCM authenticated encryption represented by `encrypted_payload`, with
  versioned keys held outside PostgreSQL.

The application reads `TWE_PROVIDER_SECRET_KEYS_JSON`, a JSON mapping of key
versions to standard-base64-encoded 32-byte keys. The separately configured
`TWE_PROVIDER_SECRET_ACTIVE_KEY_VERSION` selects the write key. Retain old keys
until all envelopes using them have been rotated. A missing keyring disables
secret storage; a partial, malformed, unknown-version, or wrong-length keyring
fails with a fixed configuration error.

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

Current official endpoint and scope behavior must be revalidated immediately
before adapter implementation. The existing
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

No Nitrado HTTP client or provider adapter is registered. When implemented, all
Nitrado-specific HTTP behavior must remain behind the unified provider registry,
use explicit timeouts, and mock HTTP in automated tests. Only ARK: Survival
Ascended may normalize to `ark_survival_ascended`. The Nitrado service ID—not an IP
address or port—will be the external resource identifier. Only useful non-secret
metadata may be retained, and raw provider responses will not be persisted.

## Database Effects and Audit Events

No new migration is required. Authenticated storage writes the existing
`provider_connection_secrets.encrypted_payload`, `encryption_nonce`, and
`key_version` columns and maintains `rotated_at` and `updated_at` during replacement
or rotation. It clears `secret_reference` when replacing an envelope. The Nitrado
workflow still writes no Provider Connection, Provider Resource, Game Server
binding, or audit event.

When the slice proceeds, remote calls must occur outside database transactions;
local connection, discovery, selection, binding, and disconnection mutations must
be transactional and idempotent. Audit events will record connection creation,
token replacement, completed discovery, selection, and disconnection without any
secret material.

## Error Handling

Secret-storage errors distinguish unavailable storage, invalid configuration,
invalid input, missing credentials, and failed ciphertext authentication. Every
message is deterministic and excludes credential and key material. Provider
authentication, scope, rate-limit, timeout, malformed-response, availability,
unsupported-game, disappearance, and binding-conflict errors remain deferred with
the adapter and routes.

## Test Coverage

Tests cover fail-closed defaults, configuration parsing and redaction, AES-256-GCM
round trips, fresh nonces, associated-data binding, tamper rejection, input limits,
ciphertext-only SQL parameters, replacement, deletion, keyring transition, and
transactional re-encryption. The PostgreSQL integration test exercises the full
store/read/replace/rotate/delete lifecycle when PostgreSQL is available. No live
Nitrado account or token is used.

The remaining Slice 2 test matrix includes Owner authorization, non-owner denial,
CSRF, mocked Nitrado outcomes,
idempotency, binding constraints, transaction boundaries, audit redaction,
frontend behavior, and existing provider/Discord/operation regressions.

## Live Validation Procedure

No live validation was performed for secret storage. A separately reviewed
read-only plan may use
a development-only token with verified minimum scopes to validate identity only if
needed, list services, identify one ARK: Survival Ascended service, and compare
normalized non-secret fields with the dashboard. The token must never enter Codex,
source control, fixtures, shell history, logs, screenshots, or documentation.

## Known Limitations

- Key distribution, backup, access control, and retirement remain deployment
  responsibilities; keys must be injected by an approved runtime secret facility.
- No Nitrado token scope has been implementation-validated.
- There is no Nitrado client, adapter, registry entry, API, UI, persistence, audit
  behavior, discovery, selection, binding, token revocation, or disconnect
  workflow.
- Existing self-hosted Genesis and Pterodactyl behavior is intentionally unchanged.

## Slice 3 Prerequisites

Slice 2 must first be fully implemented and verified. At minimum this requires
deployment approval of the key lifecycle, current official Nitrado endpoint/scope
validation, complete mocked Slice 2 coverage, migration and
transaction validation, frontend verification at required viewports, and a
security review. This work does not authorize or begin Slice 3.
