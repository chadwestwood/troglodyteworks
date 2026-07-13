CREATE TABLE IF NOT EXISTS server_operation_capability_grants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_membership_id uuid NOT NULL REFERENCES community_memberships(id) ON DELETE CASCADE,
    capability text NOT NULL,
    game_server_id uuid REFERENCES game_servers(id) ON DELETE CASCADE,
    game_instance_id uuid REFERENCES game_instances(id) ON DELETE CASCADE,
    granted_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (
        NOT (game_server_id IS NOT NULL AND game_instance_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_capability_grants_membership_id
ON server_operation_capability_grants(community_membership_id);

CREATE INDEX IF NOT EXISTS idx_capability_grants_active
ON server_operation_capability_grants(community_membership_id, capability, game_server_id, game_instance_id)
WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_capability_grant
ON server_operation_capability_grants(
    community_membership_id,
    capability,
    COALESCE(game_server_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(game_instance_id, '00000000-0000-0000-0000-000000000000'::uuid)
)
WHERE revoked_at IS NULL;
