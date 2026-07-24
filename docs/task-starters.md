# Goal-Specific Task Starters

These prompts let a fresh Codex task begin with a narrow goal while using the
same repository context. Start the task from the TWE repository so `AGENTS.md`
is loaded automatically.

## New provider connector

```text
Work in chadwestwood/troglodyteworks. Follow AGENTS.md and read
docs/project-context.md before acting.

Goal: design and implement a provider connector for <provider>.

First verify the provider's current official API, authentication, scopes,
resource-discovery model, supported games, rate limits, and mutation semantics.
Then compare those facts with TWE's provider contracts and the Nitrado,
self-hosted, Railway, and Pterodactyl implementations. Do not copy
provider-specific assumptions. Propose the smallest safe vertical slice,
identify secrets and authorization boundaries, implement it with tests, update
current documentation, and verify without exposing credentials.
```

For BisectHosting, replace `<provider>` with `BisectHosting`. Treat official
API availability as an open research question until verified.

## Frontend or journey

```text
Work in chadwestwood/troglodyteworks. Follow AGENTS.md and read
docs/project-context.md plus its frontend reading list.

Goal: <journey or page>.

Evaluate the experience for visitor, ordinary member, Community owner, World
owner, delegated operator, and consumer Discord administrator as applicable.
Keep it simple, clear, and powerful; use World in member-facing language;
preserve server-side authorization; implement reusable site-wide patterns
instead of customer-specific pages; test and verify the live route.
```

## Discord or Trog workflow

```text
Work in chadwestwood/troglodyteworks. Follow AGENTS.md and read
docs/project-context.md plus its Discord/Trog reading list.

Goal: <Trog request or Discord workflow>.

Resolve the exact guild, channel, World, provider Community, capability,
entitlement, and delegated authority before execution. The model may interpret
the request, but deterministic tools and provider adapters perform work.
Implement denial, verification, audit, and user-facing completion behavior as
part of the same slice.
```

## MCP or knowledge/RAG work

```text
Work in chadwestwood/troglodyteworks. Follow AGENTS.md and read
docs/project-context.md plus its MCP reading list.

Goal: <tool, MCP workflow, or knowledge source>.

Keep MCP tools narrow, deterministic, tenant-safe, and capability-checked.
Separate knowledge retrieval from authorization. Never give the model direct
database, shell, provider-secret, or unrestricted network access. Add protocol,
authorization, and negative tests.
```

## Production diagnosis

```text
Work in chadwestwood/troglodyteworks. Follow AGENTS.md and read
docs/project-context.md plus its production reading list.

Diagnose <symptom> using current GitHub, Railway, Cloudflare, PostgreSQL,
Discord, and provider evidence as applicable. Perform read-only checks first.
Do not involve 10.0.0.103 or the former home-server stack. Explain the cause
before making a materially different or destructive change.
```
