# Player-Owned Minecraft Connection

**Status:** Implemented proof of concept

## Purpose

A Community member may connect a Minecraft world they play in without claiming
that they own, host, or administer the Minecraft server.

This is a player observation source, not a Game Server Management Adapter. It
cannot restart the server, change settings, install mods remotely, read server
files, use RCON, or grant Server Operation Capabilities.

## First journey

1. A signed-in Member chooses **Connect a world I play in** inside a Community.
2. TWE creates a player-owned connection and displays a one-time pairing code.
3. The Member installs Trog Client and enters the code locally.
4. The mod exchanges the code for a revocable device credential.
5. The mod sends outbound-only structured presence events over HTTPS.
6. The connection owner may later approve sharing selected facts through the
   Community's existing shared Trog Discord bot installation.

For the Minecraft City proof of concept, Trog answers only player-presence
questions such as:

- Is Chad playing Minecraft City?
- Is Chad's Trog Client connected?
- When did Trog last hear from Chad's client?

These answers describe Chad's observed session. They do not describe Minecraft
City's authoritative server status or its full player population.

## Trust boundary

The Fabric client reports only what that client can observe. TWE must not label
this data as authoritative server status or imply that the Member controls the
host. Authoritative server state requires a server-side integration approved by
the server operator.

Raw logs are never uploaded. The initial allowlist is:

- `client.started`
- `client.stopped`
- `world.joined`
- `world.left`
- `heartbeat`

Event metadata may contain a user-chosen world label, a one-way SHA-256 server
fingerprint, and whether the session is multiplayer or single-player. It may not
contain chat, coordinates, server addresses, access tokens, or arbitrary log
messages.

## Credentials and consent

- Pairing codes expire after 15 minutes, are stored only as hashes, and are
  consumed once.
- Device credentials are returned once, stored only as hashes by TWE, and may be
  revoked by the connection owner. Pairing a replacement device revokes the
  previous device credential for this initial one-device proof of concept.
- A Community owner or administrator may remove a Member's feed from the
  Community, but cannot use that feed to gain Minecraft-server authority.
- Discord sharing is off by default and requires both connection-owner consent
  and current, server-side verification that the same person can administer the
  destination Discord guild. Trog's channel permissions remain controlled by
  Discord administrators.

## Implemented interfaces

- `/communities/<community>/world-connections/` is the signed-in Member journey.
- Browser APIs create, list, pair, revoke, and bind a connection to an existing
  verified Trog Discord installation. Browser mutations require TWE session
  authentication and the `X-TWE-CSRF` header.
- `/api/v1/minecraft-client/pair` exchanges one pairing code for one device
  credential. `/api/v1/minecraft-client/events` accepts only authenticated,
  allowlisted event batches. Both public client endpoints are rate-limited.
- Trog answers an approved mention or `/minecraft presence` with a response that
  explicitly identifies the source as the Member's Trog Client.

## Later slice

The proof of concept attaches player-owned bindings alongside a Discord
installation's existing hosted-World grant without changing that grant. A later
multi-context interaction model should support choosing among multiple named
player connections and hosted Worlds. When a question is ambiguous, Trog should
ask which context the person means.
