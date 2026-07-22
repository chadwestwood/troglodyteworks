CREATE TABLE IF NOT EXISTS managed_minecraft_hosting_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    requested_by uuid REFERENCES users(id) ON DELETE SET NULL,
    server_name text NOT NULL,
    provider_key text NOT NULL DEFAULT 'railway' CHECK (provider_key = 'railway'),
    game_key text NOT NULL DEFAULT 'minecraft_java' CHECK (game_key = 'minecraft_java'),
    modpack_provider text NOT NULL DEFAULT 'curseforge' CHECK (modpack_provider = 'curseforge'),
    modpack_project_id bigint NOT NULL CHECK (modpack_project_id > 0),
    modpack_file_id bigint NOT NULL CHECK (modpack_file_id > 0),
    modpack_name text NOT NULL,
    modpack_version text NOT NULL,
    memory_mb integer NOT NULL CHECK (memory_mb IN (4096, 6144, 8192)),
    estimated_monthly_min integer NOT NULL CHECK (estimated_monthly_min > 0),
    estimated_monthly_max integer NOT NULL CHECK (estimated_monthly_max >= estimated_monthly_min),
    status text NOT NULL CHECK (status IN (
        'awaiting_platform_configuration','awaiting_installation','provisioning',
        'online','failed','cancelled'
    )),
    immutable_plan jsonb NOT NULL CHECK (jsonb_typeof(immutable_plan) = 'object'),
    game_instance_id uuid REFERENCES game_instances(id) ON DELETE SET NULL,
    provider_service_id text,
    public_endpoint text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_managed_minecraft_plans_community
ON managed_minecraft_hosting_plans(community_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_managed_minecraft_active_owner
ON managed_minecraft_hosting_plans(requested_by)
WHERE status NOT IN ('cancelled','failed') AND requested_by IS NOT NULL;
