CREATE TABLE IF NOT EXISTS host_agent_pairings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash text NOT NULL UNIQUE,
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_host_agent_pairings_active
ON host_agent_pairings(community_id, expires_at) WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS host_agents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    provider_connection_id uuid NOT NULL UNIQUE REFERENCES provider_connections(id) ON DELETE CASCADE,
    name text NOT NULL,
    agent_key_hash text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'offline', 'revoked')),
    platform text,
    version text,
    last_seen_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_host_agents_community ON host_agents(community_id, created_at DESC);
