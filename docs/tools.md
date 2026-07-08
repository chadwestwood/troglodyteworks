# Troglodyte Works MCP Tools

MCP tools are safe actions the AI can request.

## Read-Only Tools

- list_customers
- get_customer
- list_services
- list_servers
- get_server_status
- get_server_settings
- read_latest_log
- list_backups
- list_mods

## Planning Tools

- suggest_restart
- suggest_backup
- suggest_mod_change
- suggest_settings_change
- diagnose_server_issue

## Action Tools

Action tools require approval.

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
