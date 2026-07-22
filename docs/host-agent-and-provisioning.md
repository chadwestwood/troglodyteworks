# Trog Host Agent and safe provisioning boundary

The Host Agent is an outbound-only bridge for a computer owned by a Community owner. It pairs with a one-time, 30-minute code and receives a separate revocable credential. It reports only normalized game status, player names, installed mod names, and bounded host metadata. The web service cannot open a shell, browse arbitrary files, or initiate an inbound connection.

Current read-only adapters:

- ARK: Survival Ascended local-process discovery.
- Minecraft Java discovery from `server.properties`, local status ping, loader detection, and installed mod filenames.

The new-server API deliberately stops at an immutable, separately approved plan. A plan identifies one active paired host, one exact CurseForge project/file pair, a bounded memory allocation, an agent-managed install root, and mandatory rollback. It does not accept commands or filesystem paths and approval does not execute anything.

Live provisioning remains disabled until all of these are present:

1. A CurseForge API credential and exact-file metadata/hash resolver.
2. A signed allowlisted agent command protocol with replay protection.
3. Disk/memory/port preflight and collision detection.
4. Staged download, archive traversal protection, malware/hash validation, and atomic promotion.
5. Verified startup plus automatic rollback.
6. A real-host acceptance test and recovery drill.

This separation prevents an LLM response or website input from becoming an arbitrary remote shell command.
