# Schedule World maintenance

## Summary

Plan a future maintenance window for one World, notify affected players, and
track the intended work. This is a focused capability specification. The
production action tool is not enabled yet.

## Permission

The proposed capability is `instance.maintenance.schedule`. A future action
must require an explicit World grant and must not infer permission from
Community membership, Discord roles, or knowledge retrieval.

## Arguments

- `instance_id` — required UUID of the affected World.
- `starts_at` — required timestamp with timezone.
- `estimated_minutes` — required positive duration.
- `summary` — required player-facing description.
- `notification_channels` — approved destinations for reminders.
- `planned_actions` — bounded list of separately supported operations.

## Confirmation

Show the World, start time, timezone, duration, notification destinations, and
planned actions. Require confirmation from an authorized operator before
saving or sending anything. Each destructive action inside the window still
requires its own applicable confirmation.

## Execution

Create a maintenance record, schedule reminders, and surface the window on the
World page. A scheduler may later initiate only explicitly supported actions
through their normal authorization and operation pipelines.

## Failure behavior

Reject past times, ambiguous timezones, invalid durations, inaccessible
channels, and unsupported planned actions. A notification failure must be
visible without silently cancelling or executing the maintenance work.

## Rollback

Before execution begins, an authorized operator may cancel the window and its
pending notifications. Completed provider actions are not reversed by
cancelling the schedule.
