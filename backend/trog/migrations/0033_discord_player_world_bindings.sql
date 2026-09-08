DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'player_world_connections_id_community_unique'
          AND conrelid = 'player_world_connections'::regclass
    ) THEN
        ALTER TABLE player_world_connections
        ADD CONSTRAINT player_world_connections_id_community_unique UNIQUE (id, community_id);
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'discord_guild_installations_id_community_unique'
          AND conrelid = 'discord_guild_installations'::regclass
    ) THEN
        ALTER TABLE discord_guild_installations
        ADD CONSTRAINT discord_guild_installations_id_community_unique UNIQUE (id, community_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS discord_player_world_bindings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_guild_installation_id uuid NOT NULL,
    player_world_connection_id uuid NOT NULL,
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    authorized_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (status <> 'active' OR revoked_at IS NULL),
    CHECK (status <> 'revoked' OR revoked_at IS NOT NULL),
    FOREIGN KEY (discord_guild_installation_id, community_id)
        REFERENCES discord_guild_installations(id, community_id) ON DELETE CASCADE,
    FOREIGN KEY (player_world_connection_id, community_id)
        REFERENCES player_world_connections(id, community_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_player_world_binding_active
ON discord_player_world_bindings(discord_guild_installation_id, player_world_connection_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_discord_player_world_binding_connection
ON discord_player_world_bindings(player_world_connection_id, status);

COMMENT ON TABLE discord_player_world_bindings IS
'Connection-owner consent to expose one player-observed world through a Trog installation controlled by a verified Discord administrator.';
