# Troglodyte Works Experience Documentation

Documentation is part of the product. Every document should identify whether it is current, historical, research, planned, implemented, partially implemented, or superseded.

## Start here

1. `current-state.md` — deployed reality and immediate constraints.
2. `production-architecture.md` — current runtime topology and boundaries.
3. `glossary.md` — shared product language.
4. `database-schema.md` — canonical persistence and object model.
5. `authentication.md` — identity and authorization rules.
6. `api-design.md` — HTTP contracts.
7. `server-operation-lifecycle.md` — contract for audited operations.
8. `vertical-slices/` — bounded implementation records.
9. `codex-guidelines.md` — implementation-agent expectations.

`engineering-tracker.md` describes a future TWE product capability. Linear is the current work-planning system of record.

## Document categories

### Current contracts

- `current-state.md`
- `production-architecture.md`
- `architecture.md`
- `glossary.md`
- `database-schema.md`
- `authentication.md`
- `api-design.md`
- `discord-integration.md`
- `server-operation-lifecycle.md`
- `services.md`

### Research

- `beacon-api.md`
- `discord-api.md`
- `nitrado-api.md`

Research informs decisions but is not, by itself, an implemented production contract.

### Historical records

Files under `Meetings/` record what was understood at the time. A later architecture decision or current-state document may supersede them without erasing their historical value.

### Vertical slices

Each vertical slice is a bounded implementation contract. Its status applies to that slice and date; later slices may extend or supersede it. Important current milestones include provider-neutral foundations, multi-provider authentication, Discord Instance access, Nitrado connection/discovery, and read-only Genesis operations.

## Source-of-truth precedence

When documents conflict, use this order:

1. accepted records in `Decisions/`;
2. `current-state.md` and `production-architecture.md` for deployed topology;
3. glossary and database schema;
4. authentication and API contracts;
5. current integration and operation contracts;
6. the latest applicable vertical slice;
7. historical meeting notes and research.

Implementation and documentation must be reconciled when they disagree. Do not silently treat an obsolete document as current, and do not rewrite historical records to make them appear predictive.

## Maintenance rule

Any change to production hosting, provider ownership, authentication, authorization, secret handling, deployment flow, or system of record must update `current-state.md`, the applicable contract, and an architecture decision in the same change.
