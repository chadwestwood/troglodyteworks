# Vertical Slice: Provider-Neutral Foundation V1

## Scope

This slice adds the provider-neutral persistence and runtime boundary used to associate a Community-owned provider account and provider resource with a TWE Game Server.

It does not implement Nitrado OAuth, Nitrado API calls, provider control operations, or browser-facing Provider Connection APIs.

## Relationship

```text
Community
  -> Provider Connection
    -> Provider Resource
      -> Game Server
        -> Game Instance (Map/World)
```

`game_servers.provider_resource_id` is nullable during migration. When present, the Provider Resource must belong to a Provider Connection owned by the same Community, and one Provider Resource may be selected by only one Game Server.

## Runtime Resolution

Status resolution is dual-path:

1. A Game Server with `provider_resource_id` uses the unified Provider Registry.
2. An unbound Game Server continues to use its existing `management_adapter`.

The `self_hosted` status adapter wraps the existing `local_asa.health` behavior without changing its response contract. Pterodactyl provisioning remains available as an optional registry capability; providers are not required to support provisioning or control operations.

Provider status calls occur only after the database lookup transaction has closed.

## Genesis Backfill

Run the schema migrations first, then execute:

```bash
backend/trog/.venv/bin/python backend/trog/scripts/backfill_genesis_provider.py
```

The backfill requires exactly one `Cohorts in the Wild -> ARK Survival Ascended -> Genesis` topology. It stops and rolls back if the topology is missing, ambiguous, or already bound to a different Provider Resource.

The command is idempotent and preserves the existing Community, Game Server, Game Instance, operation, capability-grant, Discord-grant, slug, configuration, and legacy adapter identifiers.

## Secrets

Provider Connection secrets are either an external secret reference or an authenticated encrypted payload envelope. Provider metadata is non-secret. Secret envelopes are not exposed through an API in this slice and their runtime value objects suppress secret material from representations.
