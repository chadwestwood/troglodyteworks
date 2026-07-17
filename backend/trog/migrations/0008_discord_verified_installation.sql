ALTER TABLE discord_oauth_states
ADD COLUMN IF NOT EXISTS code_verifier text,
ADD COLUMN IF NOT EXISTS discord_guild_id text;

ALTER TABLE discord_oauth_states
ADD CONSTRAINT discord_oauth_states_guild_id_check
CHECK (
    discord_guild_id IS NULL
    OR (
        discord_guild_id ~ '^[0-9]+$'
        AND length(discord_guild_id) BETWEEN 1 AND 20
    )
);

ALTER TABLE discord_instance_access_grants
ADD COLUMN IF NOT EXISTS requested_channel_ids text[] NOT NULL DEFAULT ARRAY[]::text[];

ALTER TABLE discord_instance_access_grants
ADD CONSTRAINT discord_instance_access_requested_channels_not_null
CHECK (array_position(requested_channel_ids, NULL) IS NULL);
