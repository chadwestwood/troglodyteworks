CREATE TABLE IF NOT EXISTS player_world_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    display_name text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 120),
    game_type text NOT NULL DEFAULT 'minecraft' CHECK (game_type = 'minecraft'),
    source_kind text NOT NULL DEFAULT 'fabric_client' CHECK (source_kind = 'fabric_client'),
    status text NOT NULL DEFAULT 'unpaired' CHECK (
        status IN ('unpaired', 'offline', 'ready', 'in_world', 'revoked')
    ),
    discord_sharing_enabled boolean NOT NULL DEFAULT false,
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_player_world_connections_community
ON player_world_connections(community_id);

CREATE INDEX IF NOT EXISTS idx_player_world_connections_owner
ON player_world_connections(owner_user_id);

CREATE TABLE IF NOT EXISTS player_world_pairing_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_world_connection_id uuid NOT NULL REFERENCES player_world_connections(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS idx_player_world_pairing_tokens_connection
ON player_world_pairing_tokens(player_world_connection_id);

CREATE TABLE IF NOT EXISTS player_world_devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_world_connection_id uuid NOT NULL REFERENCES player_world_connections(id) ON DELETE CASCADE,
    device_name text NOT NULL CHECK (length(device_name) BETWEEN 1 AND 120),
    device_token_hash text NOT NULL UNIQUE,
    minecraft_version text NOT NULL CHECK (length(minecraft_version) BETWEEN 1 AND 40),
    mod_version text NOT NULL CHECK (length(mod_version) BETWEEN 1 AND 40),
    paired_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz,
    revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_player_world_devices_connection
ON player_world_devices(player_world_connection_id);

CREATE TABLE IF NOT EXISTS player_world_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_world_connection_id uuid NOT NULL REFERENCES player_world_connections(id) ON DELETE CASCADE,
    player_world_device_id uuid NOT NULL REFERENCES player_world_devices(id) ON DELETE CASCADE,
    client_event_id uuid NOT NULL,
    event_type text NOT NULL CHECK (
        event_type IN ('client.started', 'client.stopped', 'world.joined', 'world.left', 'heartbeat')
    ),
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    UNIQUE (player_world_device_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS idx_player_world_events_connection_time
ON player_world_events(player_world_connection_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_player_world_events_received_at
ON player_world_events(received_at);

COMMENT ON TABLE player_world_connections IS
'Player-owned, read-only observations of worlds they play in; these records never grant hosting or server-operation authority.';

COMMENT ON COLUMN player_world_events.payload IS
'Allowlisted structured metadata only. Raw Minecraft logs, chat, coordinates, tokens, and server addresses are prohibited.';
