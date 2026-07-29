# Restart a World server

## Summary

Restart the hosting service connected to one specific TWE World. This capability
is implemented for supported Nitrado Worlds through the deterministic Trog
operation pipeline. The knowledge document explains the workflow; it does not
authorize or execute the restart.

## Permission

The caller must have `instance.restart` for the routed World. Community
membership alone is not sufficient. Authorization is evaluated again when a
confirmed request executes.

## Arguments

- `instance_id` — required UUID of the routed World.
- `reason` — optional short explanation stored with the operation.
- `discord_channel_id` — optional originating channel used for completion
  notification.

## Confirmation

Restart is a write action. Trog must show the target World and require the
authorized requester to explicitly confirm before any provider call occurs.
Expired, reused, altered, or cross-user confirmations fail closed.

## Execution

Resolve the World's approved hosting connection, create an auditable Server
Operation, request one provider restart, then monitor provider health. If the
request began in Discord, Trog reports when the World is ready again.

## Failure behavior

Provider timeouts, unavailable credentials, authorization changes, duplicate
active restarts, and failed health verification return stable, secret-free
errors. A failed provider acknowledgement is not presented as success.

## Rollback

A restart cannot be rolled back. TWE records the outcome and leaves the World
in its provider-reported state. Any follow-up start, stop, or recovery action
must be separately authorized and audited.
