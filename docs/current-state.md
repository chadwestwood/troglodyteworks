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
- The Trog worker reports a non-secret database heartbeat for admin-only runtime visibility.
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
- Nitrado rate limits, outages, and credential failures use stable secret-free API errors rather than generic application failures.

## Current operating constraints

- Live Nitrado capabilities are read-only.
- Trog restart execution remains disabled.
- Local `local_asa` documentation describes a superseded Genesis deployment and is not the production provider path.
- Provider credentials must be revocable, encrypted at rest, and never returned to the browser after storage.
- The eight-week plan and current-state documentation guide work; Linear is updated only when explicitly requested.

## Known security work

The 2026-07-22 standard security review identified three validated items:

1. application-level password-login lockout — fixed and regression-tested 2026-07-22;
2. reapply role hierarchy checks when invitation membership is approved — fixed and regression-tested 2026-07-22; and
3. authorize Instance access before provider reconciliation or other tenant-specific work — fixed and regression-tested 2026-07-22.

All three findings from the 2026-07-22 standard review now have code fixes and
targeted regression coverage.

## Immediate priorities

1. Expand reliable Nitrado read-only observability without exposing secrets or platform identifiers.
2. Extend the new non-mutating public smoke checks with safe worker, OAuth configuration, and provider-read verification.
3. Continue the eight-week plan, updating Linear only when explicitly requested.
4. Keep current-state documentation updated whenever production topology changes.
