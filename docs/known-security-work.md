# Known Security Work

**Status:** Active remediation register  
**Source:** Standard repository security review completed 2026-07-22

This file records validated security gaps without exposing exploit instructions, credentials, or sensitive production data. Linear contains the operational work items.

## Password-login abuse protection

**Severity:** Medium  
**State:** Fixed and regression-tested 2026-07-22

Local-password sign-in now records only a normalized identifier hash, serializes
attempts across application replicas, and temporarily blocks an identifier after
five failed attempts in fifteen minutes. Missing accounts still perform password
hash verification, responses remain generic, and successful sign-in clears the
failure history. The response includes `Retry-After`; OAuth sign-in is unchanged.

## Invitation approval role hierarchy

**Severity:** Medium  
**State:** Fixed and regression-tested 2026-07-22

The membership approval path re-evaluates the approver's current authority and
`can_grant_role` hierarchy immediately before membership insertion. Regression
coverage proves that a moderator cannot approve an owner-created admin invitation,
no membership is inserted, and the redemption remains pending. Legitimate owner
approval remains covered by the invitation integration suite.

## Authorize before Instance reconciliation

**Severity:** Low  
**State:** Fixed and regression-tested 2026-07-22

The Instance detail route now establishes the requesting User's Community and
Instance access before reconciliation. Unauthorized identifiers return the same
not-found response without contacting a provider or mutating Instance state. The
remaining Instance routes already authorized access before provider resolution,
reads, capability checks, or operation queries.

## Completion standard

A finding is complete only after the code is fixed, targeted regression tests pass, the relevant contract is updated, and the Linear item is read back as completed. Do not place tokens, passwords, full connection strings, or provider responses in tickets or documentation.
