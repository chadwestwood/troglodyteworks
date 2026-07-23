# Guided managed Minecraft hosting v1

## User outcome

A signed-in Discord user can choose a Community they own, select Minecraft Java,
search CurseForge modpacks, choose an exact release, choose memory, review a
monthly Railway usage estimate, accept the Minecraft EULA and beta limits, and
save an immutable installation plan, approve the final charge warning, and
start installation. TWE creates a Railway service, persistent `/data` volume,
Minecraft TCP proxy, and exact CurseForge modpack deployment. When Railway
reports the deployment healthy, TWE creates the exact game server and world
records and links the owner to that world page. Trog is then installed from
the exact world page, preserving instance-to-Discord-channel routing.

## Current production boundary

Paid infrastructure creation remains disabled until an administrator supplies
the Railway settings below. Without them, the exact plan is retained in
`awaiting_platform_configuration`; with them, it becomes resumable
`awaiting_installation`. Every Railway resource identifier is persisted as soon
as it is created, so a retry continues the same paid service instead of creating
a duplicate.

The beta enforces one active managed Minecraft plan per owner. CurseForge
project and file identities are re-resolved server-side; browser-provided names
and cost values are never trusted.

## Configuration

- `TWE_CURSEFORGE_API_KEY` enables search and validation.
- `TWE_RAILWAY_API_TOKEN` is the secret account/workspace API token.
- `TWE_RAILWAY_PROJECT_ID` and `TWE_RAILWAY_ENVIRONMENT_ID` select the approved
  TWE Railway project and production environment.
- `TWE_RAILWAY_MINECRAFT_IMAGE` defaults to `itzg/minecraft-server:latest`.
- Provider secrets remain in Railway service variables and are never returned
  to the browser or stored in the immutable plan.

## Cost language

The UI presents ranges, not guarantees. Estimates cover likely Railway memory,
CPU, storage, uptime, and traffic for 4 GB, 6 GB, and 8 GB server profiles.
Every plan requires explicit cost acknowledgment.

## Remaining beta hardening

- Add explicit cancellation and deletion after paid resource creation.
- Add a public backup/restore workflow and owner-visible Railway usage readings.
- Add richer deployment-stage diagnostics without disclosing provider details.
