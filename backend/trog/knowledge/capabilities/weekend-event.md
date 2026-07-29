# Plan a weekend event

## Summary

Coordinate a Community gaming event that may include a World, a Discord
channel, reminders, a poll, and an optional maintenance window. This is a
planning workflow assembled from smaller capabilities, not one unrestricted
provider command. The production action workflow is not enabled yet.

## Permission

The proposed planning capability is `community.event.weekend.plan`. Each
included action retains its own permission. For example, creating a poll,
scheduling maintenance, and restarting a World are authorized independently.

## Arguments

- `community_id` — required Community UUID.
- `instance_id` — optional World UUID.
- `title` — required event name.
- `starts_at` and `ends_at` — required timestamps with timezone.
- `description` — required player-facing details.
- `discord_channel_ids` — approved announcement destinations.
- `poll` — optional poll definition.
- `maintenance` — optional maintenance definition.

## Confirmation

Show one clear plan with the event time, timezone, World, channels, optional
poll, optional maintenance, and every action that would need separate
authorization. Confirm the event record and announcements; do not bundle
destructive provider approval into the event confirmation.

## Execution

Create the event, publish announcements, schedule reminders, and link any poll
or maintenance records. Execute future provider work only through the
corresponding deterministic capability pipeline.

## Failure behavior

Reject invalid time ranges, inaccessible targets, unapproved channels, and
unsupported nested actions. Preserve successful records and report partial
notification failures without claiming the whole workflow succeeded.

## Rollback

An authorized organizer may cancel the event and pending reminders. Existing
votes and completed provider operations remain auditable. Cancellation does
not reverse completed server changes.
