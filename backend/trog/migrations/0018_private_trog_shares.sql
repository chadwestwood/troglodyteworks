CREATE TABLE IF NOT EXISTS discord_instance_share_links (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    provider_community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    game_server_id uuid NOT NULL REFERENCES game_servers(id) ON DELETE CASCADE,
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE CASCADE,
    created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    capabilities text[] NOT NULL DEFAULT ARRAY['instance.status.read','instance.players.count.read','instance.players.names.read','instance.mods.names.read']::text[],
    expires_at timestamptz NOT NULL,
    max_uses integer NOT NULL DEFAULT 10 CHECK (max_uses > 0 AND max_uses <= 100),
    use_count integer NOT NULL DEFAULT 0 CHECK (use_count >= 0),
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (array_position(capabilities, NULL) IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_discord_instance_share_links_provider
ON discord_instance_share_links(provider_community_id, created_at DESC);
