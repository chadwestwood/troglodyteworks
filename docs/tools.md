# Troglodyte Works MCP Tools

**Status:** The first read-only MCP server is implemented. A listed action tool
is not a production capability unless an applicable provider adapter,
authorization contract, confirmation flow, audit lifecycle, and test suite are
implemented.

MCP tools are safe actions the AI can request.

## Implemented Read-Only Tools

- `twe_list_instances`
- `twe_get_server_status`
- `twe_get_active_players`
- `twe_get_installed_mods`
- `twe_get_operation_history`

The server uses Streamable HTTP at `/mcp`. Clients authenticate with a
revocable TWE MCP bearer token. Tokens resolve to a normal TWE User; every tool
then reuses Community membership, instance access, and capability grants.
Supplying an Instance ID from another tenant returns `NOT_FOUND`.

Player names require `instance.players.names.read` independently of player
count access. Every completed, failed, or denied tool call writes
`mcp.tool.called` to the existing audit log without provider credentials or
bearer-token material.

### Personal token API

Authenticated users manage their MCP tokens through:

- `GET /api/v1/account/mcp-tokens`
- `POST /api/v1/account/mcp-tokens`
- `DELETE /api/v1/account/mcp-tokens/{token_id}`

The raw token is returned only by the create response. Tokens are SHA-256
hashed at rest, expire, and can be revoked.

### Railway service

Deploy a second service from the same repository root with config file
`/railway.mcp.json`. It shares
`TWE_DATABASE_URL` and the provider-secret variables with the web service.
Railway's generated public domain is admitted automatically through
`RAILWAY_PUBLIC_DOMAIN`. Additional exact hosts can be supplied as a
comma-separated `TWE_MCP_ALLOWED_HOSTS` value.

## Planning Tools

- suggest_restart
- suggest_backup
- suggest_mod_change
- suggest_settings_change
- diagnose_server_issue

## Action Tools

Action tools remain planned and require approval.

- start_server
- stop_server
- restart_server
- create_backup
- restore_backup
- switch_map
- install_mod
- remove_mod
- update_server_setting
- schedule_restart

## Safety Rules

- Agents never run raw shell commands.
- Agents only use approved MCP tools.
- Destructive actions require confirmation.
- Every action is logged.
- Every config change creates a backup first.
