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

---

# Layer 6 — MCP Tools

MCP Tools provide approved actions.

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
