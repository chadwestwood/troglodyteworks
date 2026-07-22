# Troglodyte Works Current State

**Last updated:** 2026-07-22

**Status:** Current production baseline

## Product direction

Troglodyte Works Experience is a community operating layer for gaming communities. Hosting is one connected service, and infrastructure providers are replaceable. Trog is the Discord guide into approved TWE capabilities.

Genesis is an ARK: Survival Ascended Game Instance owned by Cohorts in the Wild. It is not the platform backend name.

## Production topology

- GitHub is the deployment source.
- Railway runs the Flask/Gunicorn web service.
- Railway runs Trog as a separate long-running worker.
- Railway PostgreSQL stores application state.
- Cloudflare routes `troglodyteworks.com` to Railway.
- Nitrado hosts the Cohorts in the Wild Genesis service.
- The former local server and household router are outside the production path.

See `docs/production-architecture.md` for boundaries and request flow.

## Verified capabilities

- The public site and `/health` are available at `troglodyteworks.com`.
- Local-password, Google, and Discord sign-in work in production.
- Google and Discord identities link to a canonical TWE User.
- Cohorts in the Wild has Community Membership and capability-based access.
- Trog is connected to the Cohorts Discord guild through the Railway worker.
- A service-scoped Nitrado long-life token can be validated and stored encrypted.
- Nitrado services can be discovered and bound to an existing Game Server.
- Genesis reports online through the Nitrado provider path.
- `@Trog is the server up?` returns deterministic status information.
- `@Trog who's on?` returns the available player names from Nitrado.

## Current operating constraints

- Live Nitrado capabilities are read-only.
- Trog restart execution remains disabled.
- Local `local_asa` documentation describes a superseded Genesis deployment and is not the production provider path.
- Provider credentials must be revocable, encrypted at rest, and never returned to the browser after storage.
- Linear is the current work-planning system of record; an internal TWE engineering tracker remains a future product capability.

## Known security work

The 2026-07-22 standard security review identified three validated items:

1. add application-level password-login rate limiting or lockout;
2. reapply role hierarchy checks when invitation membership is approved; and
3. authorize Instance access before provider reconciliation or other tenant-specific work.

Until those items are fixed and verified, documentation must not claim those boundaries are fully enforced.

## Immediate priorities

1. Resolve and verify the three security findings.
2. Expand reliable Nitrado read-only observability without exposing secrets or platform identifiers.
3. Add production smoke tests for the domain, OAuth callbacks, web service, worker, and provider reads.
4. Continue the eight-week plan in Linear.
5. Keep current-state documentation updated whenever production topology changes.
