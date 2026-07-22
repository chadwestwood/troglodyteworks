# Vertical Slice: Community Owner Connects a Nitrado Service V1

## Status

Secret persistence and Slice 2B token validation/service discovery were implemented
on July 17, 2026. Slice 2C explicit selection and Game Server binding were
implemented on July 18, 2026. The owner-facing connection, discovery, and selection
UI and local disconnect workflow were implemented on July 20, 2026. Nitrado-side
token revocation remains an explicit Owner responsibility.

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

The browser journey allows a signed-in Community Owner to choose
**Connect Hosting**, select Nitrado, create and submit a revocable long-life token,
choose one discovered ARK: Survival Ascended service, and bind it to a Community
Game Server. It can resume an existing connection after a reload without retaining
the token or Connection ID in browser storage. The Slice 2C API performs and
persists the selection.

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

The exact required scope is `service`. Validation calls `GET /services` directly,
so `user_info` is not required. `rootserver`, `ssh_keys`, `user_edit`, and
`service_order` are outside this slice and must not be requested.

The current official endpoint catalog was revalidated before implementation on
July 17, 2026.

## Slice 2B Route Contracts

The implemented `/api/v1` route family is:

- `POST /communities/{community_id}/hosting-connections/nitrado` validates,
  securely stores, and discovers;
- `GET /communities/{community_id}/hosting-connections/nitrado` returns the safe
  current Connection and persisted Resources for reload-safe browser setup;
- `POST /communities/{community_id}/hosting-connections/{connection_id}/discover`
  discovers with the stored credential;
- `GET /communities/{community_id}/hosting-connections/{connection_id}/resources`
  lists safe persisted resources;
- `DELETE /communities/{community_id}/hosting-connections/{connection_id}` removes
  the local credential and bindings while retaining revoked audit history.

Every route requires an authenticated Community Owner. State-changing requests
also require `X-TWE-CSRF: 1`. Responses mask credential state and never expose
secret records or token values. Local disconnection is idempotent and states that
it does not revoke the user-generated token at Nitrado.

## Slice 2C Selection and Binding Contract

The implemented selection route is:

```text
POST /communities/{community_id}/hosting-connections/{connection_id}/resources/{resource_id}/select
```

The exact request is `{ "game_server_id": "..." }`. The Connection must be an
active Community-owned Nitrado Connection. The Resource must belong to it, remain
available, have type `game_server_service`, and normalize to
`ark_survival_ascended`. The Game Server must belong to the same Community and
already represent ARK: Survival Ascended or have the matching canonical game key.

Selection transactionally assigns `game_servers.provider_resource_id`, fills the
canonical `game_key`, timestamps the selected Resource, and emits one non-secret
`provider.resource.selected` audit event. Repeating the same selection is
idempotent and does not duplicate the audit event or selection timestamp. A
Resource cannot be bound to multiple Game Servers, and a Game Server cannot be
silently rebound to another Resource. Resource-list responses include the current
safe Game Server binding so the selection remains visible after refresh.

## Slice 2B Provider Adapter and Normalization

The unified registry exposes Nitrado connection description, validation, and
credential-based discovery. The client calls only `GET /services` with a bearer
header and explicit timeout. Only an exact normalized ARK: Survival Ascended title
maps to `ark_survival_ascended`; unsupported game services retain no canonical key,
and non-game services are omitted and counted. The Nitrado service ID is the
external identifier. Only allowlisted non-secret metadata is persisted; raw
responses, websocket tokens, usernames, roles, and credentials are discarded.

## Database Effects and Audit Events

Migration `0012_nitrado_connection_uniqueness.sql` enforces one Nitrado Connection
per Community. Authenticated storage writes the existing
`provider_connection_secrets.encrypted_payload`, `encryption_nonce`, and
`key_version` columns and maintains `rotated_at` and `updated_at` during replacement
or rotation. It clears `secret_reference` when replacing an envelope. The Nitrado
Slice 2B writes the Provider Connection and Provider Resources. Slice 2C writes
the existing Game Server binding and Resource selection timestamp; no new
migration is required. Connection creation, token replacement, discovery, and
selection emit non-secret audit events. Local disconnection deletes the secret
envelope, clears Game Server bindings and Resource selection timestamps, marks
Resources unavailable, and retains the Connection as `revoked`.

Remote discovery calls occur outside database transactions. Local connection,
discovery, selection, binding, and disconnection mutations are transactional and
idempotent. Their audit events contain no secret material.

## Error Handling

Secret-storage errors distinguish unavailable storage, invalid configuration,
invalid input, missing credentials, and failed ciphertext authentication. Every
message is deterministic and excludes credential and key material. Provider
authentication, scope, rate-limit, timeout, malformed-response, and availability
errors are mapped to stable user-safe codes. Invalid stored credentials mark the
Connection `reauthorization_required`. Slice 2C maps inactive Connections,
unavailable or unsupported Resources, game mismatches, and both sides of a binding
conflict to stable user-safe errors.

## Test Coverage

Tests cover fail-closed defaults, configuration parsing and redaction, AES-256-GCM
round trips, fresh nonces, associated-data binding, tamper rejection, input limits,
ciphertext-only SQL parameters, replacement, deletion, keyring transition, and
transactional re-encryption. The PostgreSQL integration test exercises the full
store/read/replace/rotate/delete lifecycle when PostgreSQL is available. No live
Nitrado account or token is used.

Slice 2B tests cover Owner authorization, non-owner denial, CSRF, mocked valid and
invalid Nitrado outcomes, timeouts, rate limits, malformed responses, no services,
supported/unsupported/omitted services, duplicate normalization, idempotent
persistence, encrypted storage, audit redaction, and reauthorization state.
Slice 2C PostgreSQL tests cover Owner authorization, CSRF, supported selection,
persisted binding reads, canonical game assignment, idempotency, single-event
auditing, unsupported and unavailable Resources, game mismatch, and both Resource
and Game Server binding conflicts. A static frontend smoke test verifies that the
hosting page is served, uses a password input, calls the expected route family,
does not use browser local storage, and renders without `innerHTML`. Interactive
browser and viewport verification remain outstanding.

## Live Validation Procedure

No live validation was performed for secret storage. A separately reviewed
read-only plan may use
a development-only token with verified minimum scopes to validate identity only if
needed, list services, identify one ARK: Survival Ascended service, and compare
normalized non-secret fields with the dashboard. The token must never enter Codex,
source control, fixtures, shell history, logs, screenshots, or documentation.

## Known Limitations

**Post-slice production update (2026-07-22):** Genesis was subsequently migrated
to Nitrado, the discovered service was bound to the existing TWE Game Server, and
read-only status and player-name queries were verified in production. The final
bullet below describes the boundary when this slice was written, not current state.

- Key distribution, backup, access control, and retirement remain deployment
  responsibilities; keys must be injected by an approved runtime secret facility.
- Nitrado-side token revocation is not automated; after local disconnect, the
  Owner must revoke the user-generated token in Nitrado.
- At slice completion, existing self-hosted Genesis and Pterodactyl behavior was intentionally unchanged. This condition was later superseded for Genesis by the Nitrado production migration.

## Slice 3 Prerequisites

Slice 2 must first be fully implemented and verified. At minimum this requires
deployment approval of the key lifecycle, current official Nitrado endpoint/scope
validation, complete mocked Slice 2 coverage, migration and
transaction validation, frontend verification at required viewports, and a
security review. This work does not authorize or begin Slice 3.
