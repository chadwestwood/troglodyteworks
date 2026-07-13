# Discord API Research

## Purpose

This document summarizes the Discord API and its implications for Trog, the Discord-facing community assistant for TWE.

Research was verified against Discord's official developer documentation on July 13, 2026. Discord changes platform behavior and limits over time, so implementation must follow response headers and the current API reference.

## Executive Summary

Discord provides three main integration surfaces relevant to Trog:

1. **HTTP REST API** for commands, messages, guilds, channels, users, and other resources.
2. **Gateway API** for real-time events over a persistent WebSocket connection.
3. **Interactions webhooks** for receiving commands and components through a public HTTPS endpoint without a Gateway connection.

Trog currently needs the Gateway because it supports natural-language mention messages as well as slash commands. If Trog later becomes command-only, HTTP interactions could remove the persistent connection and Message Content dependency.

Discord authenticates the application and transports immutable Discord IDs. It does not replace TWE authorization. Discord role permissions, command visibility, or possession of a Discord account must never grant a TWE administrative capability by themselves.

## API Versions and Identifiers

The REST base is:

```text
https://discord.com/api
```

Clients should explicitly use version 10:

```text
https://discord.com/api/v10
```

Discord resource IDs are Snowflakes. Treat them as opaque decimal strings in JSON, application code, and PostgreSQL. JavaScript numbers cannot safely represent every 64-bit Snowflake. The ID can encode a creation timestamp, but TWE should use explicit timestamps for business logic.

HTTP clients must send a valid user agent and the content type required by the endpoint. Error payloads contain a numeric `code`, human-readable `message`, and sometimes a nested `errors` object. Code should branch on HTTP status and documented numeric codes, not message text.

## Authentication: Bot Tokens and OAuth2

### Bot token

The bot token authenticates as Trog's bot user and is used for the Gateway and most REST requests:

```http
Authorization: Bot <bot-token>
```

The bot token is a password-equivalent application secret. It must remain in secret-managed runtime configuration, never in a browser, database row intended for users, source control, logs, or Discord messages.

### OAuth2 user tokens

OAuth2 user tokens are used when TWE needs user-authorized Discord account access, such as a self-service identity-link flow. Common scopes include:

| Scope | Use |
| --- | --- |
| `identify` | Read the user's basic profile and immutable user ID. |
| `guilds` | List guilds the user belongs to. |
| `email` | Read email; TWE should not request this merely for identity linking. |
| `bot` | Install the bot in a guild. |
| `applications.commands` | Authorize application commands. |

For TWE identity linking, `identify` is normally sufficient. The callback must use state validation and then store the immutable Discord user ID. Usernames and display names are mutable and are unsuitable identity keys.

### Installation permissions

OAuth2 scopes say what category of access an application requests. Discord permissions say what the installed bot may do within a guild or channel. Trog should request only the minimum permissions needed, likely including viewing allowed channels, sending messages, reading message history when mention handling needs it, and using application commands.

Avoid requesting `ADMINISTRATOR`. It bypasses channel overwrites and makes installation harder to trust. Discord's permission system also cannot represent TWE's Community, Game Server, or Capability Grant model.

## Gateway API

The Gateway is a secure WebSocket used to receive events. A typical connection lifecycle is:

1. Fetch and cache the Gateway URL from `GET /gateway/bot`.
2. Connect to `wss://gateway.discord.gg/?v=10&encoding=json` or the returned URL.
3. Receive `HELLO` with a heartbeat interval.
4. Begin heartbeats and monitor acknowledgements.
5. Send `IDENTIFY` with the bot token, connection properties, and required intents.
6. Receive `READY` and subsequent dispatch events.
7. Persist the sequence number and session information needed to `RESUME` after recoverable disconnects.

Use a maintained Discord library rather than implementing connection, heartbeat, resume, compression, and sharding logic from scratch.

### Intents

Gateway intents select the event families and data Trog receives. They are mandatory on API v8 and later. Privileged intents are:

- `GUILD_PRESENCES`
- `GUILD_MEMBERS`
- `MESSAGE_CONTENT`

Trog's mention-based natural-language feature needs message content. Discord identifies `MESSAGE_CONTENT` as privileged, but it makes exceptions for messages that mention the application, direct messages with it, messages it sends, and message-context-command targets. Because Trog only needs addressed mentions, the implementation should verify whether the mention exception is sufficient before requesting privileged access at scale.

Slash commands do not require Message Content Intent. This is one of the strongest reasons to keep administrative workflows command-based.

### Connection limits

Important current limits include:

- 120 outbound Gateway events per connection per 60 seconds
- 1,000 `IDENTIFY` calls per application per 24 hours across all shards; `RESUME` does not count
- concurrent identify limits returned by `GET /gateway/bot`

Exhausting the daily identify limit terminates sessions and resets the bot token. Trog must prefer resume over identify, implement reconnect backoff, and prevent multiple service processes from racing to establish duplicate sessions.

Sharding becomes mandatory for large applications. The recommended shard count and session-start limits must be read from `/gateway/bot`, not hard-coded.

## Interactions and Application Commands

Discord supports slash commands, message commands, user commands, buttons, select menus, autocomplete, and modals. An interaction arrives either through the Gateway or an HTTP interactions endpoint; these delivery modes are mutually exclusive for the application.

### Command registration

Commands can be:

- **guild commands**, available immediately in one guild and best for development
- **global commands**, available across installations and appropriate for released behavior

Relevant routes are:

```text
POST /applications/{application_id}/commands
POST /applications/{application_id}/guilds/{guild_id}/commands
```

Creating a command whose name already exists in the same type and scope updates it. Discord also supports bulk overwrite, but bulk overwrite replaces the whole command set and must be used carefully.

The current command limits include 100 global slash commands, 15 global user commands, 15 global message commands, and 200 application-command creates per day per guild. Trog should maintain a small stable command tree such as `/server status`, `/server players`, and `/server restart` rather than dynamically creating commands per Game Instance.

`default_member_permissions` and guild command overrides affect discoverability and Discord-side use, but they are user experience controls only. TWE must authorize every invocation again.

### Response deadline

Trog must send an initial response or deferral within three seconds. The interaction token is then valid for follow-ups for 15 minutes.

For server operations:

1. validate the interaction and resolve the guild/channel/user
2. perform fast TWE authorization
3. defer the response, preferably ephemerally for administrative actions
4. create the Server Operation
5. update the original response with accepted/in-progress status
6. provide a stable TWE status reference for work that may exceed 15 minutes

Do not wait for a Nitrado restart or backup restore to finish before acknowledging the interaction.

### Interaction responses

Useful callback types include:

- `4` — immediate message
- `5` — deferred message with a visible loading state
- `6` — deferred component update
- `7` — immediate component message update
- `8` — autocomplete choices
- `9` — modal

The `EPHEMERAL` message flag makes a response visible only to the invoking user. It is appropriate for denials, confirmation prompts, linked-account details, and administrative progress that should not expose infrastructure data.

Always set `allowed_mentions` explicitly when including user-controlled text in a response so logs, names, or error messages cannot trigger unwanted pings.

## HTTP Interactions Alternative

Instead of receiving interactions over the Gateway, an application can configure a public Interactions Endpoint URL. The endpoint must:

- acknowledge Discord's `PING`
- validate `X-Signature-Ed25519` and `X-Signature-Timestamp` against the exact raw request body
- return `401` for an invalid signature
- meet the three-second acknowledgement deadline

Discord sends deliberate invalid-signature probes and can remove an endpoint that fails validation.

This model scales well for command-only applications, but it does not deliver general message-create events. Trog cannot switch to it without removing or separately redesigning natural-language mention handling.

## REST Rate Limits

Discord applies dynamic per-route buckets and a global bot limit. The adapter must read:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset-After`
- `X-RateLimit-Bucket`
- `X-RateLimit-Scope` on `429`
- `Retry-After` or the JSON `retry_after` value

Do not hard-code per-route limits. Routes with different top-level guild, channel, or webhook IDs can fall into different buckets even when their path shape is similar.

Current published global limits include:

- 50 authenticated REST requests per second per bot
- 10,000 invalid requests per IP per 10 minutes, where `401`, `403`, and most `429` responses count
- interaction webhook endpoints are not bound to the bot's normal global REST limit

On `429`, pause the relevant bucket for the specified duration. Avoid request storms after reconnect, and centralize rate-limit state if multiple workers share one bot token.

## Permissions and Role Hierarchy

Discord computes base guild permissions from `@everyone` and roles, then applies channel overwrites. `ADMINISTRATOR` grants all permissions and bypasses overwrites. Role hierarchy also limits whom a bot may moderate and which roles it may edit or grant.

TWE needs two separate authorization checks:

1. **Discord feasibility:** Can Trog see the channel and send the required response?
2. **TWE authority:** Does the immutable Discord user link resolve to an authorized Community Member with the required Capability Grant?

A passing Discord check must never imply a passing TWE check. This preserves the rules in `docs/discord-integration.md` and `docs/trog-bot-workflow.md`.

## Trog-Specific Data Flow

For every interaction or addressed mention, persist or derive:

| Discord value | TWE use |
| --- | --- |
| `application_id` | Verify the event targets Trog. |
| `guild_id` | Resolve `discord_guild_installations`. |
| `channel_id` | Resolve channel capability policy. |
| immutable `user.id` | Resolve `discord_identities`. |
| `interaction.id` or message ID | Idempotency and audit correlation. |
| command name/options | Map to a fixed TWE intent and capability. |

Never authorize using username, nickname, discriminator, message text, or a client-supplied TWE user ID.

Interactions can be delivered or processed more than once across retries and restarts. Use the interaction Snowflake as an idempotency key so a duplicate `/server restart` cannot create two Server Operations.

## Security and Privacy Requirements

- keep the bot token and OAuth client secret in secret-managed environment configuration
- rotate the bot token immediately if it appears in logs or source control
- validate HTTP interaction signatures before parsing or acting
- use immutable Snowflake IDs as strings
- escape output and restrict `allowed_mentions`
- avoid logging raw message content, interaction tokens, authorization headers, or sensitive option values
- request only necessary bot permissions, OAuth scopes, and Gateway intents
- use ephemeral responses for sensitive administrative information
- cap message and embed content and split long diagnostic output safely
- enforce TWE authorization independently of Discord permissions
- create a durable Server Operation before any external administrative action

## Recommended Next Steps

1. Keep the current Gateway architecture while mention handling remains required.
2. Confirm the minimum intents actually used by the installed library and disable unused intents.
3. Test mention-only content access without broad Message Content approval.
4. Register guild commands in development and promote the stable command tree to global commands.
5. Add interaction-ID idempotency before enabling restart execution.
6. Defer administrative interactions immediately and hand work to the Server Operation lifecycle.
7. Build self-service Discord identity linking with OAuth2 `identify`, state validation, expiration, and explicit unlinking.
8. Add rate-limit telemetry that records buckets and retry delays without recording tokens or message content.

## Verification Limits

- Official documentation was reviewed, but no live Discord API requests were made.
- No command registration, Gateway connection, permission calculation, or interaction webhook was exercised in this research task.
- Current Trog behavior was evaluated from repository documentation, not end-to-end browser and Discord testing.
- Privileged-intent availability depends on the application's installation reach and Discord review status and must be checked in the Developer Portal.

## Official Sources

- [Discord API reference](https://docs.discord.com/developers/reference)
- [Discord Gateway](https://docs.discord.com/developers/events/gateway)
- [Discord interactions overview](https://docs.discord.com/developers/interactions/overview)
- [Receiving and responding to interactions](https://docs.discord.com/developers/interactions/receiving-and-responding)
- [Discord application commands](https://docs.discord.com/developers/interactions/application-commands)
- [Discord OAuth2 and permissions](https://docs.discord.com/developers/platform/oauth2-and-permissions)
- [Discord permission reference](https://docs.discord.com/developers/topics/permissions)
- [Discord rate limits](https://docs.discord.com/developers/topics/rate-limits)

