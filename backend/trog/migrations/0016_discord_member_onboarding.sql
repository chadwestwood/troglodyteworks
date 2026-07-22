CREATE TABLE IF NOT EXISTS discord_user_guild_memberships (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    discord_user_id text NOT NULL CHECK (discord_user_id ~ '^[0-9]+$'),
    discord_guild_id text NOT NULL CHECK (discord_guild_id ~ '^[0-9]+$'),
    discord_guild_name text,
    verified_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    PRIMARY KEY (user_id, discord_guild_id),
    CHECK (length(discord_user_id) BETWEEN 1 AND 20),
    CHECK (length(discord_guild_id) BETWEEN 1 AND 20)
);

CREATE INDEX IF NOT EXISTS idx_discord_user_guild_memberships_active
ON discord_user_guild_memberships(user_id, expires_at);

ALTER TABLE communities ADD COLUMN IF NOT EXISTS discord_setup_guild_id text;
CREATE UNIQUE INDEX IF NOT EXISTS idx_communities_discord_setup_guild_id
ON communities(discord_setup_guild_id) WHERE discord_setup_guild_id IS NOT NULL;
