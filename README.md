# Troglodyte Works Experience

Troglodyte Works Experience (TWE) is a community operating layer for gaming communities. Hosting is one connected service; the Community, its members, permissions, identity, and history remain the durable center of the product.

Trog is TWE's Discord guide. It answers approved questions through deterministic, capability-checked tools while TWE remains the authority for identity, Community Membership, provider connections, and operations.

## Production status

Active development. The current production path is:

```text
GitHub repository
  -> Railway web service (Flask/Gunicorn)
  -> Railway worker service (Trog Discord bot)
  -> Railway PostgreSQL

Cloudflare DNS
  -> https://troglodyteworks.com
  -> Railway web service

Nitrado
  -> Cohorts in the Wild / Genesis
  -> read-only status and player information
```

Verified production capabilities include:

- local-password, Google, and Discord sign-in;
- canonical TWE accounts with linked external identities;
- Community Membership and capability-based authorization;
- Discord guild installation and provider-approved Instance access;
- encrypted Nitrado credential storage, service discovery, and resource binding;
- read-only Genesis status and player-name responses through Trog; and
- separate Railway web and long-running Discord worker services.

The former in-house server and `10.0.0.103` are not part of the current production path. Historical local-server documentation is retained only where it explains prior decisions.

## Current systems of record

- Source and deployment input: GitHub
- Runtime: Railway
- DNS and public edge: Cloudflare
- Database: Railway PostgreSQL
- Game hosting for Genesis: Nitrado
- Work planning: the eight-week plan and current-state documentation; Linear is updated only when explicitly requested
- Architecture and implementation contracts: `docs/`

## Repository layout

```text
backend/trog/   Flask application, migrations, tests, Trog worker, and provider adapters
site/           Server-rendered/static browser experience
docs/           Current contracts, research, and vertical slices
Blueprint/      Product principles and constitutional direction
Decisions/      Architecture decision records
Ideas/          Deferred ideas
Meetings/       Historical planning records
Research/       Research indexes and supporting material
```

## Local development

Local development is optional and does not serve production traffic.

1. Copy `backend/trog/.env.example` to `backend/trog/.env` and supply non-production values.
2. Install `backend/trog/requirements.txt` in an isolated Python environment.
3. Use a dedicated PostgreSQL test database whose name ends in `_test`.
4. Apply migrations with `backend/trog/scripts/migrate.py`.
5. Run tests with:

   ```bash
   backend/trog/.venv/bin/python -m pytest -q
   ```

Never place production tokens, passwords, OAuth secrets, provider credentials, or database URLs in source control or command history.

## Deployment model

Railway builds from `backend/trog`. Database migrations run as the web service's pre-deploy step. The web service runs Gunicorn and exposes HTTP on Railway's assigned port. The worker runs `python -m twe.discord_bot.service` and intentionally exposes no HTTP endpoint.

Production changes flow through reviewed repository commits and Railway deployments. They are not made by editing the former local server.

After Railway activates a web deployment, run the non-mutating public checks:

```bash
python backend/trog/scripts/production_smoke.py
```

The checks cover the custom domain, deterministic health response, homepage,
sign-in page, and anonymous authentication boundary. They never sign in, create
OAuth state, contact a game provider, or modify production data.

## Operational safety

Current Nitrado integration is read-only for live status, player information, and the configured ASA mod list. Destructive or disruptive actions—including restart, stop, restore, configuration mutation, and mod changes—must remain unavailable until their authorization, confirmation, audit, provider, and recovery contracts are explicitly implemented and reviewed.

## Documentation

Start with:

- `docs/current-state.md` for deployed reality;
- `docs/production-architecture.md` for runtime topology;
- `docs/database-schema.md` for the canonical persistence model;
- `docs/authentication.md` for identity and authorization boundaries; and
- `docs/README.md` for document status and precedence.
