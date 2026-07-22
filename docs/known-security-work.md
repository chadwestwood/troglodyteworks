# Known Security Work

**Status:** Active remediation register  
**Source:** Standard repository security review completed 2026-07-22

This file records validated security gaps without exposing exploit instructions, credentials, or sensitive production data. Linear contains the operational work items.

## Password-login abuse protection

**Severity:** Medium  
**State:** Validated; remediation pending

Application-level password sign-in needs rate limiting, progressive delay, temporary lockout, or an equivalent abuse-resistant control. Provider and edge limits are defense in depth, not a replacement for an application control with tests and observable outcomes.

## Invitation approval role hierarchy

**Severity:** Medium  
**State:** Validated; remediation pending

The membership approval path must re-evaluate the approver's current authority and `can_grant_role` hierarchy immediately before membership insertion. Authority captured when an invitation was created is not sufficient because roles and actors can change.

## Authorize before Instance reconciliation

**Severity:** Low  
**State:** Validated; remediation pending

Instance routes must establish tenant/Instance access before reconciliation, provider reads, or other resource-specific work. This reduces cross-tenant timing and side-effect exposure and makes the authorization boundary explicit.

## Completion standard

A finding is complete only after the code is fixed, targeted regression tests pass, the relevant contract is updated, and the Linear item is read back as completed. Do not place tokens, passwords, full connection strings, or provider responses in tickets or documentation.

