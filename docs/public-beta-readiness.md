# Public Beta Readiness

## Supported beta path

1. A participant creates a TWE account and connects a verified Discord identity.
2. A Community owner invites the participant or provisions a Community through the guided beta process.
3. The owner connects a revocable, service-scoped Nitrado token and selects one ASA service.
4. The owner completes the provider-approved Discord installation and channel scope.
5. Members use `/server help`, `/server status`, `/server count`, `/server players`, `/server mods`, and `/server settings` within their approved capabilities.

## Operational readiness

- `/health` remains the shallow Railway process health check.
- `/health/ready` verifies the web process can reach PostgreSQL and that the Trog worker heartbeat is current.
- `.github/workflows/production-monitor.yml` checks readiness every ten minutes. A failed run is the durable alert signal and contains no secret or provider response content.
- The admin runtime view separates website/API, PostgreSQL, and Discord worker state.
- Every pushed change runs tracked-secret policy checks, dependency auditing, migrations, and the complete PostgreSQL-backed regression suite.

## Abuse boundaries

- Password login retains identifier-based protection across Railway replicas.
- Sensitive public writes use a database-backed, hashed-network-identifier rate limit shared across replicas.
- Trog natural-language responses require a direct mention.
- Discord requests are limited per immutable user and guild, and generated replies disable mentions.

## Deliberate beta limits

- Server restart execution remains disabled even when the capability is authorized.
- The first hosting integration is Nitrado ASA; unsupported services remain visible but cannot be attached.
- Community creation is still guided rather than fully self-service.
- Production alerts currently use GitHub Actions failure notifications; a dedicated paging destination can be added after beta traffic establishes the appropriate escalation policy.

## Launch check

- Run the production monitor manually once after deployment.
- Confirm Google and Discord sign-in on the canonical domain.
- Confirm a real Nitrado-connected instance reports ready.
- Confirm all six read/help commands in an approved Discord channel.
- Confirm an unapproved channel and an unlinked user receive denials without data leakage.
- Confirm the admin runtime view shows three distinct healthy components.
