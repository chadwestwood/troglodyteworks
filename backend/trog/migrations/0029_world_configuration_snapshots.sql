CREATE TABLE IF NOT EXISTS world_configuration_snapshots (
    id uuid PRIMARY KEY,
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE CASCADE,
    provider_key text NOT NULL,
    source_kind text NOT NULL,
    settings jsonb NOT NULL,
    checked_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT world_configuration_snapshots_settings_array
        CHECK (jsonb_typeof(settings) = 'array')
);

CREATE INDEX IF NOT EXISTS world_configuration_snapshots_instance_checked_idx
    ON world_configuration_snapshots (game_instance_id, checked_at DESC, created_at DESC);
