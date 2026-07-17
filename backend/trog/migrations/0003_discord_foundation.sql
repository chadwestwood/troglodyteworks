CREATE TABLE IF NOT EXISTS discord_guild_installations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_guild_id text NOT NULL UNIQUE CHECK (discord_guild_id ~ '^[0-9]+$'),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    game_server_id uuid NOT NULL REFERENCES game_servers(id) ON DELETE CASCADE,
    installed_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(discord_guild_id) BETWEEN 1 AND 20)
);

CREATE INDEX IF NOT EXISTS idx_discord_guild_installations_community_id
ON discord_guild_installations(community_id);

CREATE INDEX IF NOT EXISTS idx_discord_guild_installations_game_server_id
ON discord_guild_installations(game_server_id);

CREATE TABLE IF NOT EXISTS discord_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_user_id text NOT NULL UNIQUE CHECK (discord_user_id ~ '^[0-9]+$'),
    user_id uuid UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    linked_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(discord_user_id) BETWEEN 1 AND 20),
    CHECK ((user_id IS NULL AND linked_at IS NULL) OR user_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_discord_identities_user_id
ON discord_identities(user_id) WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS discord_channel_policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_guild_installation_id uuid NOT NULL REFERENCES discord_guild_installations(id) ON DELETE CASCADE,
    discord_channel_id text NOT NULL CHECK (discord_channel_id ~ '^[0-9]+$'),
    capability_category text NOT NULL CHECK (capability_category IN ('read', 'administrative')),
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(discord_channel_id) BETWEEN 1 AND 20),
    UNIQUE (discord_guild_installation_id, discord_channel_id, capability_category)
);

CREATE INDEX IF NOT EXISTS idx_discord_channel_policies_lookup
ON discord_channel_policies(discord_guild_installation_id, discord_channel_id, capability_category);
