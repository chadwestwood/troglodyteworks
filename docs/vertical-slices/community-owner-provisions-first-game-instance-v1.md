# Vertical Slice: Community Owner Provisions First Game Instance (V1)

## Purpose

A Community owner can request a brand-new managed game Instance from within TWE.

This slice is isolated from existing manually installed Genesis infrastructure and local ASA runtime controls.

## Implemented Scope

Supported in this version:

- Game: ARK: Survival Ascended
- Map: The Island
- Hosting engine: Pterodactyl Panel + Wings
- Runtime isolation: managed by Pterodactyl/Wings

Out of scope in this version:

- Existing Genesis server
- LocalASAAdapter provisioning
- Save migration and transfers
- Billing
- Multi-node and multi-game orchestration
- Mod management and backups
- Direct file/browser/console/SFTP exposure

## API

- GET /api/v1/game-catalog
- POST /api/v1/communities/{community_id}/instances
- GET /api/v1/instances/{instance_id}
- GET /api/v1/server-operations/{operation_id}

## Backend Design

A TWE-owned HostingProvider boundary is introduced in services:

- hosting.py defines HostingProvider, InstanceSpec, ProviderInstanceState
- hosting_providers.py resolves the configured provider implementation
- pterodactyl_provider.py implements the first provider
- instance_provisioning.py orchestrates creation and status reconciliation

The rest of TWE depends on provider-neutral status mapping and never consumes raw Pterodactyl response shapes.

## Provisioning Lifecycle

1. Owner requests provisioning with allowlisted game and map.
2. TWE creates a Game Instance row and Server Operation row (capability: instance.provision).
3. TWE calls the provider to create the backing server.
4. Provider server identifier is persisted on the instance.
5. Instance and operation are reconciled through provider status polling on read endpoints.
6. Operation transitions to completed or failed with persisted result message.

## Idempotency

Provisioning requests are tracked in instance_provisioning_requests using:

- community_id
- requested_by
- idempotency_key

Repeated requests with the same key return the original instance and operation instead of creating duplicates.

## Security

- Only Community owners can provision.
- Browser input is restricted to allowlisted game and map keys.
- TWE controls all node/image/startup/allocation/environment settings server-side.
- Pterodactyl administrative credentials remain backend-only.
- No owner Docker or Wings shell exposure is provided by this slice.

## Persistence

Migration 0010 adds:

- instance_provisioning_requests table
- game_instances columns: hosting_provider, provider_instance_id, provider_state, provisioning_error

## Frontend Flow

Community page now includes a Host a Game panel for owners:

1. Select game and map from GET /game-catalog.
2. Confirm provisioning.
3. Submit POST /communities/{id}/instances.
4. Poll instance and operation endpoints for visible progress.
5. Resume progress tracking after refresh using remembered operation and instance IDs.

Non-owner members see explanatory copy and cannot submit provisioning.
