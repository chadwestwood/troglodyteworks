CREATE UNIQUE INDEX IF NOT EXISTS idx_provider_connections_one_nitrado_per_community
ON provider_connections(community_id, provider_key)
WHERE provider_key = 'nitrado';
