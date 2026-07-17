CREATE TABLE IF NOT EXISTS instance_provisioning_requests (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    requested_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    idempotency_key text NOT NULL,
    game_key text NOT NULL,
    map_key text NOT NULL,
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE CASCADE,
    server_operation_id uuid NOT NULL REFERENCES server_operations(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (community_id, requested_by, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_instance_provisioning_requests_community
ON instance_provisioning_requests(community_id);

CREATE INDEX IF NOT EXISTS idx_instance_provisioning_requests_instance
ON instance_provisioning_requests(game_instance_id);

ALTER TABLE game_instances
ADD COLUMN IF NOT EXISTS hosting_provider text,
ADD COLUMN IF NOT EXISTS provider_instance_id text,
ADD COLUMN IF NOT EXISTS provider_state text,
ADD COLUMN IF NOT EXISTS provisioning_error text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_game_instances_provider_identity
ON game_instances(hosting_provider, provider_instance_id)
WHERE provider_instance_id IS NOT NULL;