# Trog Personality

**Status:** Implemented v1 contract

## Purpose

Trog has one installation-scoped voice that gives simple Discord conversation
a consistent character without changing facts, authorization, World routing,
confirmations, or provider operations.

The five user-facing choices are deliberately plain language:

| Stored value | Discord label | Meaning |
| --- | --- | --- |
| `friendly` | Friendly | Warm and conversational; the default |
| `direct` | Direct | Brief and literal |
| `sarcastic` | Sarcastic | Helpful with restrained dry humor |
| `professional` | Professional | Polished and formal |
| `enthusiastic` | Enthusiastic | Upbeat and energetic |

Themed aliases are not used in commands, settings, help text, or audit history.

## Supported conversation

After the normal direct-mention and rate-limit checks, Trog handles these
high-confidence social intents locally:

- presence, such as `@Trog are you there?`;
- wellbeing, such as `@Trog how are you today?`;
- name origin;
- identity;
- greetings, thanks, farewells, and praise.

Each installation, preset, and intent cycles through its complete curated
response bank before repeating. These replies use no OpenAI call, knowledge
retrieval, provider request, World setting, or Server Operation.

The matcher accepts only reviewed whole-message forms. A greeting attached to
a World question does not intercept that question. Factual settings, status,
players, mods, restarts, and mod additions continue through their existing
deterministic intent, World-routing, capability, confirmation, provider, and
audit paths.

`@Trog what can you do?` and `/server help` produce a scoped, conversational
description of what Trog can do for that member in that channel. The reply
does not expose slash commands or implementation-oriented language. The active
voice changes the short introduction, not the capability result.

## Commands and authority

The command surface is:

- `/trog personality show`;
- `/trog personality preview <preset>`;
- `/trog personality set <preset>`;
- `/trog personality reset`.

All replies are private to the command user. Any member may show or preview a
voice. Only the live Discord guild owner, verified from the Discord interaction
guild and immutable user ID at command time, may set or reset it. A cached
browser permission, Discord role, TWE entitlement, or model output cannot
authorize the change.

V1 does not delegate personality management. Delegation requires a reviewed
installation-scoped capability design; it must not reuse a World operation
grant or create an informal Discord-role bypass.

## Persistence and audit

`discord_guild_installations.personality_preset` stores the active value and
defaults existing and new installations to `friendly`. PostgreSQL constrains it
to the five reviewed values.

Each saved change creates `discord.trog_personality.updated` in `audit_logs`
with the installation target, previous preset, new preset, and immutable
Discord actor ID. If the actor has a linked `discord_identities` row, the audit
also links the canonical TWE User. No message content, token, credential,
provider identifier, or provider response is stored.

## Safety boundary

Personality is presentation only. It never changes:

- the connected World or provider resource;
- a setting name, value, freshness, or verification result;
- effective member capabilities;
- confirmation requirements;
- operation execution or verification;
- error and security disclosures.

V1 deliberately does not rewrite factual or operational results with a model.
This keeps the existing verified data and authorization paths intact while the
new conversational layer is evaluated.
