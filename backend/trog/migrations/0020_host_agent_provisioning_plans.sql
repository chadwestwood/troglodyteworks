CREATE TABLE IF NOT EXISTS host_agent_installation_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    host_agent_id uuid NOT NULL REFERENCES host_agents(id) ON DELETE CASCADE,
    requested_by uuid REFERENCES users(id) ON DELETE SET NULL,
    approved_by uuid REFERENCES users(id) ON DELETE SET NULL,
    game_key text NOT NULL CHECK (game_key IN ('minecraft_java')),
    server_name text NOT NULL,
    modpack_provider text NOT NULL CHECK (modpack_provider IN ('curseforge')),
    modpack_project_id bigint NOT NULL CHECK (modpack_project_id > 0),
    modpack_file_id bigint NOT NULL CHECK (modpack_file_id > 0),
    memory_mb integer NOT NULL CHECK (memory_mb BETWEEN 2048 AND 32768),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft','awaiting_approval','approved','executing','verifying','completed','failed','rolled_back')),
    immutable_plan jsonb NOT NULL CHECK (jsonb_typeof(immutable_plan) = 'object'),
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_host_agent_installation_plans_community
ON host_agent_installation_plans(community_id, created_at DESC);
