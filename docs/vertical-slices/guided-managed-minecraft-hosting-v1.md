# Guided managed Minecraft hosting v1

## User outcome

A signed-in Discord user can choose a Community they own, select Minecraft Java,
search CurseForge modpacks, choose an exact release, choose memory, review a
monthly Railway usage estimate, accept the Minecraft EULA and beta limits, and
save an immutable installation plan. The final screen explains that Trog is
installed from the exact world page after the server exists, preserving
instance-to-Discord-channel routing.

## Current production boundary

This slice deliberately stops before paid infrastructure creation. It does not
hold a Railway platform token and does not imply that a server was installed.
Plans use `awaiting_platform_configuration` until a separately reviewed Railway
provisioning adapter can create a service, persistent `/data` volume, TCP proxy,
and the `itzg/minecraft-server` environment safely.

The beta enforces one active managed Minecraft plan per owner. CurseForge
project and file identities are re-resolved server-side; browser-provided names
and cost values are never trusted.

## Configuration

- `TWE_CURSEFORGE_API_KEY` enables search and validation.
- The key remains in Railway service variables and is never returned to the UI.

## Cost language

The UI presents ranges, not guarantees. Estimates cover likely Railway memory,
CPU, storage, uptime, and traffic for 4 GB, 6 GB, and 8 GB server profiles.
Every plan requires explicit cost acknowledgment.

## Next implementation slice

Add a Railway provisioning adapter with narrowly scoped credentials,
idempotency, rollback, volume/TCP verification, audit events, and a final
transition that creates the TWE `game_server` and `game_instance`. Only then may
the UI offer a paid **Install server** action.
