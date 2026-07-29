# Troglodyte Works Current State

**Last updated:** 2026-07-29

**Status:** Current production baseline

## Product direction

Troglodyte Works Experience is a community operating layer for gaming communities. Hosting is one connected service, and infrastructure providers are replaceable. Trog is the Discord guide into approved TWE capabilities.

Genesis is an ARK: Survival Ascended Game Instance owned by Cohorts in the Wild. It is not the platform backend name.

## Production topology

- GitHub is the deployment source.
- Railway runs the Flask/Gunicorn web service.
- Railway runs Trog as a separate long-running worker.
- The Trog worker reports a non-secret database heartbeat for admin-only runtime visibility.
- The readiness endpoint verifies the website, PostgreSQL, and current Trog worker heartbeat; GitHub checks it every ten minutes.
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
- Installed ASA mods are read from Nitrado and enriched through the shared
  mod-name catalog.
- Exact, delegated operator capabilities can authorize a Nitrado restart or
  mod addition for one routed World; restart monitoring reports back to the
  originating Discord channel.
- Consumer Discord guilds can request provider-approved, World-specific Trog
  access without becoming owners of the provider Community or World.
- Member-facing navigation uses World while backend routes and persistence
  retain the Game Instance model.
- Community, user, and World identity images are supported by the current
  member experience.
- The first read-only MCP server is available at `/mcp` and reuses TWE identity,
  tenant, and capability checks.
- Guided managed-Minecraft planning supports CurseForge exact-file selection,
  cost acknowledgement, and resumable Railway provisioning behind platform
  configuration and beta gates.
- The outbound-only self-hosted Host Agent foundation reports bounded,
  normalized status, player, and mod information.
- Nitrado rate limits, outages, and credential failures use stable secret-free API errors rather than generic application failures.
- Sensitive public writes use a hashed-identifier, database-backed limiter shared by Railway replicas.
- Trog natural-language requests require a direct mention and are burst-limited per Discord user and guild.
- Trog routes supported Discord requests through a deterministic
  intent → permission → validation → confirmation → tool pipeline. Restart and
  mod-add requests cannot reach their provider tool until an authorized user
  repeats the explicit confirmation command.
- The public beta page documents the supported identity, Community, hosting, installation, and command-verification path.
- GitHub pull requests and pushes to `main` run backend regressions, a Python dependency audit, and tracked-secret/configuration policy checks.

## Current operating constraints

- Nitrado writes are limited to the specifically authorized restart and mod-add
  workflows. Arbitrary settings, file access, backups, restores, console
  commands, and other mutations remain disabled.
- MCP remains read-only.
- Paid managed-Minecraft resource creation remains platform-configuration and
  beta gated.
- Local `local_asa` documentation describes a superseded Genesis deployment and is not the production provider path.
- Provider credentials must be revocable, encrypted at rest, and never returned to the browser after storage.
- Linear remains the work-planning system of record but is updated only when explicitly requested.

## Known security work

The 2026-07-22 standard security review identified three validated items:

1. application-level password-login lockout — fixed and regression-tested 2026-07-22;
2. reapply role hierarchy checks when invitation membership is approved — fixed and regression-tested 2026-07-22; and
3. authorize Instance access before provider reconciliation or other tenant-specific work — fixed and regression-tested 2026-07-22.

All three findings from the 2026-07-22 standard review now have code fixes and
targeted regression coverage.

## Immediate priorities

1. Keep the redesigned visitor, Community, World, Discord, and account journeys
   simple, clear, reusable, and permission-aware.
2. Harden the guided managed-Minecraft and self-hosted beta paths before broader
   customer use.
3. Add hosting providers through the provider-neutral connector boundary,
   beginning with official API/authentication research.
4. Expand safe production verification for worker, OAuth, Discord, MCP, and
   provider behavior.
5. Continue the eight-week plan, updating Linear only when explicitly requested.
6. Keep current-state documentation updated whenever production behavior or
   topology changes.
