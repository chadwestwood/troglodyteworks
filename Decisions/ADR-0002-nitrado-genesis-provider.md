# ADR-0002: Nitrado Hosts the Production Genesis Instance

**Status:** Accepted  
**Date:** 2026-07-22

## Decision

The Cohorts in the Wild Genesis Instance is hosted by Nitrado and bound to TWE through a discovered Provider Resource. TWE uses a revocable, service-scoped long-life credential stored through the encrypted provider-secret boundary.

## Consequences

- The former `local_asa` Genesis binding is superseded.
- Current production capabilities are read-only status and player information.
- Restart, stop, restore, configuration, mod, and other disruptive operations remain disabled until separately designed, authorized, audited, and verified.
- Community identity and history remain provider-neutral.

