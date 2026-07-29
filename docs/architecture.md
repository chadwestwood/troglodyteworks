# Troglodyte Works Architecture

The living, plain-language system map is available at:

```text
https://troglodyteworks.com/architecture/
```

Its five views distinguish production truth from active foundations and future
intent:

- Overview
- Data rails
- Action rails
- Knowledge
- Roadmap

The map is maintained as repository-native HTML, CSS, and structured JavaScript
under `site/architecture/`, `site/css/architecture.css`, and
`site/js/architecture.js`. It must not display secrets, private provider
identifiers, credentials, or tenant data.

## Philosophy

Troglodyte Works is built from the outside in.

The architecture begins with the Member experience.

Technology exists to support Journeys.

Journeys support Communities.

Communities create value.

Genesis naming rule:

Genesis is an ARK instance name under a Community game service path.

Genesis is not the Troglodyte Works backend or platform name.

---

# Layer 1 — Experience

Everything begins with a Journey.

Examples:

- Join Friends
- Manage Game Servers
- Explore Troglodyte Works

A Journey asks one question at a time and reveals only the next relevant step.

---

# Layer 2 — Communities

Communities are the center of the platform.

A Community may contain:

- Members
- Roles
- Servers
- Events
- Polls
- Automations

Most features exist within the context of a Community.

---

# Layer 3 — Services

Services provide capabilities.

Examples:

- Server Management
- Hosting
- Discord Integration
- Monitoring
- Automation
- Guidance

Services should remain modular.

New Services should be added without redesigning the platform.

---

# Layer 4 — Guides

Guides help Members accomplish goals.

Guides:

- Explain
- Recommend
- Observe
- Adapt

Guides do not directly perform actions.

They request Tools.

The interface must remain usable even when Guides are disabled.

---

# Layer 5 — AI

AI provides reasoning.

Examples:

- Diagnose issues
- Recommend actions
- Explain settings
- Coordinate workflows

AI never directly changes the operating system.

Trog's language boundary is a versioned, typed contract:

1. TWE resolves the authenticated Discord user, guild, channel, Community,
   World, and effective capabilities before contacting a model.
2. Only bounded, tenant-scoped facts and approved citations cross the boundary.
   Provider credentials, session material, and unrelated tenant data are
   rejected.
3. The OpenAI Responses API returns strict structured output: a grounded
   answer, clarification, refusal, or typed action proposal.
4. A proposal is not execution. TWE independently checks its World and
   capability, requires confirmation, reauthorizes the caller, and invokes only
   an approved provider tool.
5. Model failures, malformed output, and unexpected tool calls fail closed to a
   deterministic response.

The gateway is configuration-gated and the Discord handoff remains disabled
until its end-to-end authorization and fallback behavior are production
verified.

---

# Layer 6 — MCP Tools

The first MCP service provides audited, tenant-safe read tools over Streamable
HTTP. Its bearer tokens map to real TWE Users, and tool execution reuses the
same Community membership and instance capability checks as the web and
Discord surfaces.

Implemented reads:

- Resolve the caller's Communities and Instances
- Read server status
- Read active-player count and separately authorized names
- Read installed mods
- Read operation history
- Retrieve approved knowledge excerpts with citations

The knowledge rail is deliberately separate from authorization and action
execution:

1. an approved source manifest controls what can be indexed;
2. Markdown headings become citation-preserving chunks;
3. PostgreSQL full-text search and pgvector rank relevant evidence;
4. Community-scoped sources require current Community membership; and
5. the MCP tool returns evidence and citations, never a permission decision or
   provider mutation.

MCP action tools are still gated. The shared deterministic operation pipeline
and explicit Discord confirmation rules are implemented, but MCP writes remain
disabled until each action has a provider adapter, audit contract, and
end-to-end authorization coverage.

Examples:

- Restart Server
- Read Logs
- Install Mods
- Create Backup
- Schedule Event

Every Tool has a clearly defined responsibility.

---

# Layer 7 — Infrastructure

Infrastructure executes the work.

Includes:

- Linux
- Docker
- Game Servers
- Databases
- Storage
- Monitoring
- Networking

Infrastructure should remain replaceable.

Replacing infrastructure should not change the Member experience.

---

# Design Principles

Every architectural decision should answer:

Does this make the product:

- calmer?
- simpler?
- more powerful?

If not, reconsider the design.

---

# Long-Term Vision

The architecture should support new:

- Games
- Communities
- Services
- Guides
- Integrations

without requiring fundamental redesign.

The platform should evolve by adding capabilities rather than increasing complexity.
