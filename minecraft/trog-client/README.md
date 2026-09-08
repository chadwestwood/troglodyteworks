# Trog Client

Trog Client is a client-only Fabric mod that reports a small, structured view of
your own Minecraft session to Troglodyte Works. It does not require access to the
Minecraft host and cannot control the server.

## Proof-of-concept setup

1. Start Minecraft once with the mod installed. Trog Client creates
   `config/trog-client.json` and remains inactive.
2. Create a player-owned Minecraft connection in TWE and copy its one-time
   pairing token into `pairingToken`.
3. Set `worldLabel` and `serverAddress` to the exact world you consent to
   observe, then restart Minecraft.

The server address stays on the player's computer. Trog Client sends only its
SHA-256 fingerprint, the chosen world label, and presence events. It never sends
raw logs, chat, coordinates, credentials, or activity from other configured
servers.

## Build

```text
./gradlew build
```

The client mod is written to `build/libs/trog-client-0.1.0.jar`.
