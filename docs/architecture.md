# Troglodyte Works Architecture

## Customer Portal

The customer-facing website.

Responsibilities:

- Login
- Dashboard
- Billing
- Server list
- Backups
- Settings
- AI Chat

---

## AI Layer

The AI never directly edits files.

Instead it communicates with MCP servers.

The AI's responsibility is reasoning.

The MCP servers' responsibility is taking actions.

---

## MCP Servers

Each MCP server specializes in one area.

Examples:

- Customer MCP
- Game MCP
- Linux MCP
- Billing MCP
- Monitoring MCP

Each MCP server exposes tools.

---

## Game Servers

Each customer's servers run independently.

Supported games include:

- Ark Survival Ascended
- Ark Survival Evolved
- Minecraft
- Palworld

Future games can be added without changing the AI.

---

## Storage

Stores:

- Customer accounts
- Server profiles
- Game templates
- Logs
- Backups
- Billing information

---

## Monitoring

Collects:

- CPU usage
- RAM usage
- Disk usage
- Player count
- Server status
- Crash reports

---

## Automation

Handles:

- Scheduled restarts
- Automatic backups
- Mod updates
- Notifications
