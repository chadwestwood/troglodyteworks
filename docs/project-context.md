# TWE Project Context

**Status:** Current task bootstrap  
**Last reconciled:** 2026-07-24

This is the shortest reliable entry point for a fresh TWE task. It summarizes
the durable context that previously existed only across long chat threads.
Detailed contracts remain authoritative according to `docs/README.md`.

## Product in one paragraph

Troglodyte Works Experience (TWE) is a community operating layer for gaming
communities. A Community contains people, roles, connected game services, and
playable Worlds. Trog is the Discord-facing guide that answers questions and
triggers deterministic, capability-checked workflows. Hosting providers are
replaceable integrations; the Community, its ownership, its Worlds, its
permissions, and its history remain durable TWE concepts.

The experience standard is:

> **Simple, clear, and powerful.**

Ask one understandable question at a time, show the next relevant choice, and
hide implementation language from ordinary members.

## Shared vocabulary

- **Community:** the durable group of people and resources.
- **Game Server:** the managed game service/container.
- **World:** member-facing term for a playable map, save, realm, or environment.
- **Game Instance / `game_instance`:** backend and persistence term for a World.
- **Provider Community:** the TWE Community that owns or controls a World.
- **Consumer Discord Guild:** a Discord server permitted to use selected Trog
  capabilities for a World it does not own.
- **Provider Connection:** a Community-owned credential relationship with a
  host such as Nitrado.
- **Provider Resource:** a discovered host-side service bound to a TWE Game
  Server.
- **Capability:** one exact server-side permission, such as reading status,
  restarting a World, or adding a mod.
- **Entitlement:** a product-plan feature. Entitlement never substitutes for
  owner-granted authority.

See `glossary.md`, `data-model.md`, and `products-and-entitlements.md`.

## Production truth

```text
GitHub main branch
  -> Railway Docker build
     -> web service: Flask + Gunicorn
     -> worker service: Trog Discord Gateway worker
     -> Railway PostgreSQL

Cloudflare
  -> https://troglodyteworks.com
  -> Railway web service

Connected providers
  -> Nitrado: Cohorts in the Wild / ARK Genesis
  -> Railway: managed Minecraft provisioning foundation
  -> self-hosted: outbound-only Host Agent foundation
```

Important boundaries:

- GitHub is the deployment source.
- Root `railway.json` uses the root `Dockerfile`.
- The web pre-deploy step runs `python scripts/migrate.py`.
- `/health` is shallow process health; `/health/ready` includes PostgreSQL and
  Trog worker freshness.
- The worker is not an HTTP service and should not receive an HTTP health check.
- PostgreSQL is the production authority for identity, Communities,
  Memberships, Worlds, provider bindings, Discord installations/grants,
  sessions, operations, audits, and MCP access.
- Production is not served from a home network or `10.0.0.103`.

Read `production-architecture.md`, `current-state.md`, and
`Decisions/ADR-0001-railway-production.md` for detail.

## Current implemented foundations

- Local-password, Google, and Discord authentication with one canonical TWE
  User and linked external identities.
- Multi-Community membership, ownership, invitations, role/capability grants,
  Community and World identity images, and member-facing World pages.
- One shared Discord application installed into multiple guilds.
- Exact World-to-guild/channel routing through Discord installations, Instance
  Access Grants, capability allowlists, and channel policy.
- Public read-only Trog questions for status, players, settings, and installed
  mods where the grant permits them.
- Owner-approved operator delegation for exact Worlds.
- Authorized Nitrado restart and mod-add workflows with provider verification,
  operation/audit records, and restart-ready channel notification.
- Encrypted, revocable Nitrado credential storage; service discovery and
  provider-resource binding.
- Site-wide ASA mod-name catalog used to turn provider IDs into member-facing
  names. Authorized mod-add requests accept either a numeric CurseForge
  project ID or an exact ASA mod name; uncatalogued references are verified
  through the CurseForge API and persisted to the shared JSON catalog before
  Nitrado is changed.
- First read-only MCP server at `/mcp`, with bearer tokens mapped to real TWE
  Users and reuse of TWE tenant/capability checks.
- Guided managed-Minecraft planning, CurseForge exact-file selection, Railway
  cost acknowledgement, resumable Railway resource provisioning, and World
  creation after provider health is confirmed. Paid provisioning remains
  configuration- and beta-gated.
- Outbound-only self-hosted Host Agent pairing and normalized read-only reports.
- Public architecture diagrams at
  `https://troglodyteworks.com/architecture/`.

The implementation and tests are the final evidence for exact capability
availability. Do not infer a write capability merely because a provider API
supports it.

## Provider connector architecture

Provider integrations are registered in:

- `backend/trog/twe/services/provider_contracts.py`
- `backend/trog/twe/services/provider_registry.py`
- `backend/trog/twe/services/provider_resolution.py`
- `backend/trog/twe/services/provider_secret_storage.py`

Current registrations:

| Provider key | Current purpose |
| --- | --- |
| `nitrado` | credential validation, discovery, reads, authorized restart/mod add |
| `self_hosted` | Host Agent-backed status, players, and mod reads |
| `railway` | managed Minecraft provisioning/restart foundation |
| `pterodactyl` | provisioning foundation |

BisectHosting is not implemented. A Bisect connector should first verify
Bisect's current official integration surface and authentication model, then
fit capabilities into the provider contracts. Do not copy Nitrado endpoints,
scope assumptions, response shapes, or credential behavior.

For provider work, read:

1. `services/provider_contracts.py` and `services/provider_registry.py`;
2. `database-schema.md` provider tables and ownership constraints;
3. `authentication.md`;
4. `server-operation-lifecycle.md`;
5. `known-security-work.md`;
6. the closest provider research and vertical slice;
7. the existing provider adapter and tests as an implementation example, not a
   universal contract.

## Current site map

### Visitor-facing

- `/` — landing page; signed-in users are routed to My Communities.
- `/explore/` — discover or join.
- `/products/` and `/products/<plan>/` — product/entitlement explanation.
- `/beta/` — supported beta path.
- `/architecture/` — living system maps and roadmap.
- `/auth/sign-in.html` and `/auth/register.html` — identity entry.
- `/invite/<token>/` and `/discord/share/<token>/` — scoped invitations.

### Signed-in member experience

- `/communities/` — My Communities, create, discover, and join entry.
- `/communities/<community>/` — Community home and World overview.
- `/communities/<community>/game-servers/<game>/worlds/<world>/` — canonical
  member-facing World page.
- The legacy `/instances/<world>/` route serves the same World experience for
  compatibility; new member-facing links should say and use **World**.
- `/discord/request-access/` — exact World-to-Discord installation, approval,
  channel, and capability workflow.
- `/profile/`, `/account/`, `/onboarding/`, `/hosting/new/` — user identity,
  account connections, guided entry, and managed hosting.

### Owner/operator surfaces

- `/communities/<community>/hosting/`
- `/communities/<community>/invitations/`
- World settings and exact operation pages
- `/admin/` for platform-only visibility

Browser pages are static/reusable shells backed by Flask APIs. Dynamic
Community and World routes are served from shared templates; do not create a
new hard-coded page for each customer.

## Authorization model

An action requires both:

```text
product entitlement
AND
authority granted for the exact Community / Game Server / World / Discord scope
```

World owners define the maximum capabilities they expose. A consumer Discord
administrator may install Trog and delegate within that maximum but cannot
expand it. Ordinary users in an enabled channel receive only public/read
capabilities. Write operations require the exact delegated capability and
server-side authorization.

Every provider mutation should use the Server Operation lifecycle:

```text
request -> authorize -> confirm when required -> execute deterministic adapter
-> verify provider result -> audit -> report
```

## Security rules

- Never request that a customer paste a production secret into chat.
- Secrets belong in Railway variables or encrypted provider-secret envelopes.
- Provider credentials are never returned to the browser after storage.
- Browser input does not prove ownership, Discord installation, provider state,
  or permission.
- Authorize tenant access before reconciliation or provider calls.
- Keep MCP tools narrow and deterministic; the model requests tools but does
  not receive direct database, shell, or provider credentials.
- Run `python scripts/security_check.py` and applicable tests before publishing.
- Review `known-security-work.md` before changing auth, tenant resolution,
  provider secrets, Discord access, uploads, or MCP.

## Source, deployment, and verification workflow

Normal production change path:

```text
local checkout -> tests -> commit -> GitHub main -> Railway deploy
-> safe production verification
```

Use `backend/trog/scripts/production_smoke.py` for non-mutating public checks.
Use provider-, OAuth-, Discord-, or worker-specific verification for those
surfaces; do not fake them through the shallow health endpoint. Inspect Railway
deployment logs when a build, migration, boot, or runtime check fails.

Do not deploy by editing the old local server. Do not assume a commit is live
until Railway has activated it and the relevant production behavior is
verified.

## Planning and documentation

- Linear is the current eight-week backlog and completion record.
- Update Linear only when Chad explicitly requests it.
- `engineering-tracker.md` is a future product idea, not the current backlog.
- Meeting notes are historical.
- Accepted ADRs and current contracts outrank old vertical slices.
- Recent code may move faster than documentation; reconcile the current
  contract when a task discovers drift.

## Focused reading by task

### New provider connector or hosting integration

Read this file, `production-architecture.md`, `database-schema.md`,
`authentication.md`, `server-operation-lifecycle.md`,
`host-agent-and-provisioning.md`, the provider contracts/registry, and the
closest existing adapter tests.

### Discord or Trog behavior

Read `discord-integration.md`, `trog-bot-workflow.md`,
`vertical-slices/trog-external-instance-access-v1.md`,
`products-and-entitlements.md`, and Discord authorization tests.

### Frontend, sitemap, navigation, or onboarding

Read `design-principles.md`, `voice-and-language.md`, `user-journeys.md`,
`glossary.md`, and inspect current reusable page templates and browser scripts.

### Authentication, roles, or permissions

Read `authentication.md`, `database-schema.md`,
`products-and-entitlements.md`, `known-security-work.md`, and the applicable
integration tests.

### MCP, tools, or knowledge/RAG

Read `architecture.md`, `tools.md`, `mcp_server.py`, `mcp_tools.py`, and
`known-security-work.md`. MCP is the controlled action/query boundary. The
implemented citation-backed knowledge rail uses approved sources, PostgreSQL
full-text search, and pgvector through `twe_search_knowledge`. Retrieval remains
read-only and must never become an authorization or action path.

### Database or migration

Read `database-schema.md`, the latest migrations, affected route/service tests,
and the ownership/tenant constraints in the applicable vertical slice. Use
forward-only migrations.

### Railway, deployment, or production incident

Read `production-architecture.md`, root `railway.json`, root `Dockerfile`,
health/readiness code, production smoke checks, and recent deployment-related
commits.
