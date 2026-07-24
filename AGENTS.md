# Troglodyte Works Task Bootstrap

This file is the required starting point for every Codex task in this
repository. It exists so goal-specific tasks can share the same durable project
context without depending on another chat transcript.

## Read first

Before planning or changing code, read:

1. `docs/project-context.md` — concise product, production, deployment, sitemap,
   provider, and work-planning context.
2. `docs/README.md` — documentation categories and precedence.
3. The task-specific documents listed in `docs/project-context.md`.

When documentation and code disagree, inspect the current implementation and
recent commits, then reconcile the applicable current document in the same
change. Do not silently rely on a historical meeting note or superseded
vertical slice.

## Non-negotiable project facts

- TWE is a community operating layer for gaming communities, not merely a
  hosting control panel.
- The product experience should be **simple, clear, and powerful**.
- Member-facing language uses **World**. Backend and database code may continue
  using `game_instance` and instance identifiers.
- GitHub `chadwestwood/troglodyteworks` is the production source.
- Railway runs the web service, Trog worker, and PostgreSQL.
- Cloudflare routes `troglodyteworks.com` to Railway.
- The former household server, router, Apache/NGINX stack, remote VS Code
  session, and `10.0.0.103` have no production authority.
- Linear is the planning system of record, but update it only when Chad
  explicitly asks.
- Never place credentials, tokens, database URLs, OAuth secrets, private
  provider identifiers, or customer data in source, documentation, fixtures,
  screenshots, logs, or chat output.

## Normal implementation workflow

1. Identify the user journey and exact authority boundary.
2. Inspect the applicable current contract, implementation, migrations, and
   tests.
3. Prefer provider-neutral contracts over provider-specific business logic.
4. Implement the smallest complete vertical slice.
5. Add or update tests in proportion to risk.
6. Update current documentation when behavior, topology, authorization,
   persistence, provider ownership, or deployment changes.
7. Verify locally, publish only when the request authorizes implementation, and
   verify the resulting Railway deployment through safe public checks.

Do not use Linear as a per-step checklist. Do not infer that a subscription
grants authority over someone else's Community or World. Do not let browser
input, Discord roles, or an AI response bypass server-side capability checks.

## Task routing

Use the focused reading lists in `docs/project-context.md`:

- provider connector or hosting work;
- Discord/Trog work;
- frontend or navigation work;
- authentication and permissions;
- MCP, tools, or future RAG work;
- database or migration work;
- production, Railway, or incident work.

Reusable goal-specific prompts are in `docs/task-starters.md`.
