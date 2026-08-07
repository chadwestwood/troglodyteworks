# Trog Bot Workflow

**Status:** Implemented foundation; expanding provider workflows

**Verified production interactions:** status, player count, player names,
settings, installed mods, bounded restart, and authorized ASA mod addition for
the Nitrado-hosted Genesis World.

## Purpose

Trog is the Discord-facing community assistant for Troglodyte Works.

Trog allows Discord members to interact with community and game-server capabilities without requiring them to log directly into the Troglodyte Works website.

Trog is one shared Discord application installed across multiple Discord servers. Each Discord server is connected to its own Troglodyte Works community, game servers, instances, permissions, and configuration.

---

## Core Principles

1. Trog must know who is asking.
2. Trog must know which Discord community the request came from.
3. Trog must know which provider Troglodyte Works community and exact instance are exposed to that Discord server.
4. Trog must authorize every requested capability before performing it.
5. Read-only public actions may use natural-language mentions.
6. Administrative or destructive actions should use structured slash commands.
7. Dangerous actions require confirmation.
8. Every administrative action must be auditable.
9. Discord roles may supplement authorization but must not be the only source of authority.
10. Secrets must never be stored in source control or sent through Discord messages.
11. A consumer Discord guild may receive approved read capabilities without owning the provider Community's instance.
12. Provider owners must be able to revoke external Discord access without deleting either community or installation.

---

## Supported Interaction Types

### Natural-language mentions

Examples:

```text
@Trog is the server up?
@Trog how many players are online?
@Trog who's on?
@Trog what mods are installed?
@Trog map settings
@Trog restart
@Trog add 930381 to the map
@Trog add Silent Structures to the world
@Trog are you there?
@Trog how are you today?
@Trog where does your name come from?
```

Presence, wellbeing, name-origin, identity, greeting, thanks, farewell, and
praise questions are matched against reviewed whole-message forms and answered
from the installation's rotating curated response bank. This social path does
not call a provider, OpenAI, MCP, RAG, or a Server Operation. A message that
also asks a World question is not consumed as small talk.

The active voice is Friendly, Direct, Sarcastic, Professional, or Enthusiastic.
Asking Trog which personalities it has, or asking to change without naming a
choice, displays those five choices as a native Discord button card, with the
active choice marked. The live Discord guild owner can use the card,
conversational requests, or `/trog personality`; other members may show or
preview the choices and receive private owner guidance if they click a change
button. Personality never grants a capability or alters the deterministic
response body for verified facts and operations.

For external provider-owned access, replies identify the provider-owned instance:

```text
Cohorts in the Wild - Genesis is up and ready for players.
```

Installed-mod questions require `instance.mods.names.read`. Production Genesis resolves
that capability through its bound Nitrado resource and reads the ordered ASA mod list
from the provider's game-server details. Trog uses provider-supplied display names
and the shared ASA catalog. An authorized mod-add request accepts a project ID or
an exact mod name. For an unknown ID, Trog asks CurseForge for its canonical name;
for an unknown name, Trog searches the ASA CurseForge catalog for an exact
name/slug match and obtains the numeric project ID. The verified pair is written
to the shared JSON catalog before the numeric ID is sent to Nitrado. No LLM or
MCP investigator is involved in this path yet. Approximate and ambiguous results
fail safely rather than guessing. Other providers remain provider-dependent.
Reading the catalog does not itself grant mod management; mod addition requires
its separate delegated capability and operation lifecycle.

Natural-language questions about current configuration require
`instance.settings.read`. Trog resolves the Discord channel to one exact World,
refreshes that World's bound Nitrado settings and saved INI files, and answers
only from the promoted verified revision for the same `game_instance_id`.
Provider form defaults, stale revisions, ambiguous duplicate values, and IDs
mentioned by a user or model cannot select or substitute configuration.
Setting-name retrieval also fails closed: exact word/acronym tokens produce a
structured topic and qualifier intent, and only catalog-eligible settings may
be ranked for the answer. Substring collisions cannot cross this eligibility
gate, and the model cannot choose raw INI keys directly.

When one reviewed topic still has multiple independent meanings, Trog asks one
short deterministic question before answering. The choices must be supported
by the verified settings for that exact World, show no more than two focused
options plus **all**, and contain no model-generated expansion or next-step
offer. XP is the first reviewed ambiguity policy. A member can answer with a
specific choice such as **crafting XP** or explicitly request **all XP
multipliers**. That answer is a new request and repeats exact World routing,
authorization, freshness, and eligibility checks; no shared conversational
state is trusted across Discord members or channels.
If the member names one singular setting and that semantic name exists, Trog
returns only that setting rather than adding related variants.

The `map settings` summary combines server status, online player names, and
the active mod list. Each section retains its corresponding read capability
check; the combined command does not broaden the requester's access.

Trog must not describe the instance as owned by the consumer Discord guild.

Player-list responses contain display usernames only. Provider payload fields,
RCON row numbers, immutable platform account IDs, and Nitrado service identifiers
must be removed before composing a Discord reply.

Discord account linking is handled through the provider-neutral external identity model. A User who signed up with Google or local credentials must connect Discord to the same TWE User before Discord guild authority can be verified. Linking Discord only proves the Discord user identity; Community Membership, provider approval, Instance Access Grants, and capability allowlists remain separate authorization steps.
