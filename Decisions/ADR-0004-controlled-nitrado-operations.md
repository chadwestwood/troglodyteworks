# ADR-0004: Controlled Nitrado Operations Through Trog

**Status:** Accepted  
**Date:** 2026-07-22

## Context

ADR-0002 established Nitrado as the production provider for Cohorts in the Wild
Genesis and initially limited TWE to read-only calls. Subsequent product
decisions authorized two bounded operations: restarting the routed World and
adding an ASA mod by immutable mod ID.

## Decision

TWE may execute Nitrado restart and mod-add operations only when all of the
following are true:

- Discord resolves exactly one active World through its installation, access
  grant, and channel policy;
- the requesting immutable Discord identity has the exact delegated capability;
- the provider Community still owns the resolved World;
- the operation uses the deterministic Nitrado adapter and encrypted provider
  credential boundary;
- the result is verified against Nitrado and recorded through operation/audit
  records; and
- restart requests notify the originating channel when the World becomes ready
  or when monitoring times out.

This decision does not authorize arbitrary settings, files, backups, restores,
console commands, mod removal, or unrestricted provider calls.

## Consequences

- Production Nitrado integration is no longer entirely read-only.
- Ordinary Discord users retain read-only capabilities.
- Consumer Discord administrators cannot exceed the provider owner's approved
  capability ceiling.
- The MCP server remains read-only until write tools receive their own reviewed
  confirmation and operation contracts.
- Provider failures and unconfirmed settings fail closed and return stable,
  secret-free messages.
