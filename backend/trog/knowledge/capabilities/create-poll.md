# Create a Community poll

## Summary

Create a bounded poll for a Community or one of its Worlds and publish it to
approved surfaces such as a selected Discord channel. This specification is
retrievable now; the production action tool is not enabled yet.

## Permission

The proposed capability is `community.poll.create`. Publishing to Discord also
requires an active Trog channel route for the relevant Community or World.
Retrieving this document never grants either permission.

## Arguments

- `community_id` — required Community UUID.
- `instance_id` — optional World UUID for World-specific polls.
- `question` — required player-facing question.
- `options` — two to ten unique choices.
- `closes_at` — optional timestamp with timezone.
- `discord_channel_ids` — one or more approved publication channels.
- `allow_multiple` — optional boolean, default false.

## Confirmation

Preview the exact question, options, closing time, and destinations. Require
confirmation from the creator before publication.

## Execution

Persist the poll, publish one canonical poll message per approved destination,
and retain message identifiers so results can be reconciled and audited.

## Failure behavior

Reject empty or duplicate options, inaccessible Communities or Worlds,
unapproved channels, and closing times in the past. Partial publication must
report exactly which destinations succeeded.

## Rollback

Before votes exist, an authorized creator may delete the poll and published
messages. After voting begins, close the poll early and retain an audit record
rather than erasing results.
