# ADR-0005: Instance-scoped configuration registry

**Status:** Accepted

**Date:** 2026-08-03

## Context

Nitrado exposes both control-panel settings data and saved game INI files. Form
metadata can include defaults that look like current values, so an answer based
on a flattened provider response can be wrong. Trog also serves multiple Discord
guilds, channels, provider accounts, services, and Worlds; a provider service ID
supplied by a user or model is not an authorization boundary.

## Decision

Trog configuration reads require the separate public capability
`instance.settings.read`. Authorization resolves the Discord guild and channel
to one active Instance Access Grant and exact `game_instance_id` before any
provider request.

The application then resolves that instance's Game Server, Provider Resource,
Provider Connection, and encrypted credential. The Nitrado service ID is read
only from that bound Provider Resource and is stored as provenance, never
accepted from Discord text, model output, or a settings query.

Each refresh downloads the provider's explicit settings resource and all saved
`.ini` files exposed through its read-only file-server bookmarks. It stores an
append-only revision, artifact hashes, and explicit assignment observations.
Sensitive values are redacted before persistence. Defaults are never created.
Duplicate conflicting assignments remain in the audit record but are excluded
from answers.

A database lineage trigger rejects revisions whose instance, Provider Resource,
Provider Connection, provider key, or external resource do not match the live
binding. A composite foreign key and promotion trigger allow an instance's
current pointer to reference only a verified revision belonging to that same
instance. Cached reads accept only a promoted verified revision no more than 15
minutes old; factual settings questions refresh first.

## Consequences

- A Discord user can see settings only for the World authorized in that channel.
- Different Worlds and different customers can use separate Nitrado credentials
  without sharing configuration state.
- Saved INI evidence outranks a control-panel summary when both name the same
  setting.
- Missing, stale, conflicted, unverified, or unreadable evidence produces an
  explicit inability to verify; Trog does not substitute a default.
- Raw INI file contents and provider credentials are not stored in the registry.
  Artifact hashes and redacted observations preserve provenance without creating
  another plaintext-secret store.
