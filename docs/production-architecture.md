# Production Architecture

**Status:** Current  
**Last verified:** 2026-07-22

## Topology

```text
Browser
  -> Cloudflare DNS and TLS
  -> troglodyteworks.com
  -> Railway web service
       -> Flask/Gunicorn
       -> Railway PostgreSQL
       -> Google OAuth
       -> Discord OAuth and REST API
       -> Nitrado REST API

Discord Gateway
  <-> Railway Trog worker
       -> Railway PostgreSQL
       -> approved provider adapters

GitHub
  -> Railway build and deployment
```

## Service responsibilities

### Web service

The web service owns browser routes, API routes, authentication callbacks, Community workflows, provider connection workflows, and deterministic HTTP health responses. Database migrations execute before a new web deployment becomes active.

### Trog worker

The worker maintains the Discord Gateway connection and handles supported mentions and commands. It is a long-running worker, not an HTTP service, and therefore has no Railway HTTP health check. It writes a non-secret liveness heartbeat to PostgreSQL; the admin-only runtime-health API treats heartbeats older than two minutes as stale.

### PostgreSQL

Railway PostgreSQL is the authoritative production database for Users, external identities, Communities, Memberships, Game Servers, Game Instances, provider connections and resources, Discord installation/access grants, sessions, operations, and audit records.

### Cloudflare

Cloudflare owns public DNS and edge routing for `troglodyteworks.com`. Railway terminates the application route behind the configured custom domain.

### Nitrado

Nitrado is the current provider for the Cohorts in the Wild Genesis Instance. TWE stores a revocable, service-scoped credential through the provider-secret boundary and binds the discovered Nitrado service to the existing TWE Game Server. Current production calls are read-only status and player queries.

## Change path

Production code changes follow:

```text
working copy -> Git commit -> GitHub -> Railway build -> pre-deploy migration -> deployment
```

Direct edits to the former in-house server are not a deployment mechanism.

## Deployment verification

`backend/trog/scripts/production_smoke.py` verifies the custom domain, web
health contract, public pages, and anonymous authentication boundary without
creating sessions or mutating data. OAuth callbacks require a real provider
round trip, the Discord worker has no HTTP endpoint, and Nitrado reads require
authorized tenant context; those surfaces must use their dedicated production
verification procedures rather than being faked by the public smoke command.

## Security boundaries

- Secrets stay in Railway variables or encrypted provider-secret storage.
- OAuth callback URLs must exactly match the registered production URLs.
- Discord identity, installation, Community Membership, capability grant, and provider approval are separate authorities.
- Browser input never proves Discord ownership, installation, or provider state.
- Read access must be authorized before tenant-specific reconciliation or provider calls.
- Disruptive provider operations require a separate reviewed lifecycle and are currently disabled.
