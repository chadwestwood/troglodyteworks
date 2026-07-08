# Troglodyte Works Domain Model

The platform is built around business objects.

## Customer

A person with one account.

Owns one or more Services.

---

## Service

A hosted product.

Examples:

- ARK Survival Ascended
- Minecraft
- Palworld
- Docker Host

A Service owns one or more Servers.

---

## Server

A running instance.

Properties:

- Name
- Status
- Game
- Version
- Map
- Settings
- Mods
- Backups
- Logs
- Resources

---

## Map

A playable world.

Examples:

- Genesis
- Ragnarok
- Lost Colony
- The Island

---

## Mod

A downloadable extension.

Properties:

- ID
- Name
- Version
- Dependencies
- Enabled

---

## Backup

A snapshot of a server.

Properties:

- Date
- Size
- Reason
- Restore Point

---

## Tool

An action exposed through MCP.

Examples:

- start_server
- stop_server
- backup_server
- install_mod
- read_logs

---

## Agent

An AI employee.

Agents never directly edit the operating system.

Agents use Tools.
