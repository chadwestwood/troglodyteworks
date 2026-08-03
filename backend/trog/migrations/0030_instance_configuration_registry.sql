-- Instance-scoped, append-only configuration registry.
-- Provider service identifiers are provenance only. Every read and promotion is
-- anchored to the authorized game_instance_id.

DO $$
DECLARE
    old_constraint text;
BEGIN
    SELECT con.conname
    INTO old_constraint
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'discord_instance_access_grant_capabilities'
      AND con.contype = 'c'
    LIMIT 1;

    IF old_constraint IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE discord_instance_access_grant_capabilities DROP CONSTRAINT %I',
            old_constraint
        );
    END IF;
END $$;

ALTER TABLE discord_instance_access_grant_capabilities
ADD CONSTRAINT discord_instance_access_grant_capability_check CHECK (
    capability IN (
        'instance.status.read',
        'instance.settings.read',
        'instance.players.count.read',
        'instance.players.names.read',
        'instance.mods.names.read',
        'instance.mods.write',
        'instance.restart.execute'
    )
);

-- Existing read-only routes receive the new read capability so the rollout does
-- not silently remove settings access. New routes use the updated defaults below.
INSERT INTO discord_instance_access_grant_capabilities
    (discord_instance_access_grant_id, capability)
SELECT DISTINCT c.discord_instance_access_grant_id, 'instance.settings.read'
FROM discord_instance_access_grant_capabilities c
JOIN discord_instance_access_grants g ON g.id = c.discord_instance_access_grant_id
WHERE c.capability = 'instance.status.read'
  AND c.revoked_at IS NULL
  AND g.status = 'active'
ON CONFLICT DO NOTHING;

ALTER TABLE discord_instance_share_links
ALTER COLUMN capabilities SET DEFAULT ARRAY[
    'instance.status.read',
    'instance.settings.read',
    'instance.players.count.read',
    'instance.players.names.read',
    'instance.mods.names.read'
]::text[];

UPDATE discord_instance_share_links
SET capabilities = array_append(capabilities, 'instance.settings.read')
WHERE array_position(capabilities, 'instance.status.read') IS NOT NULL
  AND array_position(capabilities, 'instance.settings.read') IS NULL;

CREATE TABLE IF NOT EXISTS world_configuration_revisions (
    id uuid PRIMARY KEY,
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE RESTRICT,
    provider_resource_id uuid NOT NULL REFERENCES provider_resources(id) ON DELETE RESTRICT,
    provider_connection_id uuid NOT NULL REFERENCES provider_connections(id) ON DELETE RESTRICT,
    provider_key text NOT NULL,
    external_resource_id text NOT NULL,
    observed_at timestamptz NOT NULL,
    parser_version text NOT NULL,
    snapshot_hash text NOT NULL CHECK (snapshot_hash ~ '^sha256:[0-9a-f]{64}$'),
    validation_state text NOT NULL CHECK (validation_state IN ('verified', 'rejected')),
    validation_report jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(validation_report) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, game_instance_id),
    UNIQUE (
        game_instance_id, provider_resource_id, provider_connection_id, snapshot_hash
    )
);

CREATE INDEX IF NOT EXISTS world_configuration_revisions_instance_observed_idx
ON world_configuration_revisions (game_instance_id, observed_at DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS world_configuration_artifacts (
    id uuid PRIMARY KEY,
    revision_id uuid NOT NULL,
    game_instance_id uuid NOT NULL,
    source_role text NOT NULL CHECK (source_role IN ('provider_settings', 'saved_ini')),
    source_locator text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^sha256:[0-9a-f]{64}$'),
    size_bytes integer NOT NULL CHECK (size_bytes >= 0),
    encoding text,
    retrieved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, revision_id, game_instance_id),
    UNIQUE (revision_id, source_role, source_locator),
    FOREIGN KEY (revision_id, game_instance_id)
        REFERENCES world_configuration_revisions(id, game_instance_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS world_configuration_observations (
    id uuid PRIMARY KEY,
    revision_id uuid NOT NULL,
    game_instance_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    source_role text NOT NULL CHECK (source_role IN ('provider_settings', 'saved_ini')),
    source_locator text NOT NULL,
    source_section text,
    source_key text NOT NULL,
    occurrence_index integer NOT NULL DEFAULT 0 CHECK (occurrence_index >= 0),
    line_number integer CHECK (line_number IS NULL OR line_number > 0),
    raw_value text,
    raw_value_hash text CHECK (
        raw_value_hash IS NULL OR raw_value_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    typed_value jsonb,
    value_type text CHECK (
        value_type IS NULL OR value_type IN ('boolean', 'integer', 'number', 'string')
    ),
    parse_state text NOT NULL CHECK (parse_state IN ('parsed', 'invalid')),
    explicitly_set boolean NOT NULL DEFAULT true,
    is_sensitive boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (is_sensitive AND raw_value IS NULL AND raw_value_hash IS NULL AND typed_value IS NULL)
        OR (NOT is_sensitive AND raw_value IS NOT NULL AND raw_value_hash IS NOT NULL)
    ),
    UNIQUE (artifact_id, source_section, source_key, occurrence_index),
    FOREIGN KEY (artifact_id, revision_id, game_instance_id)
        REFERENCES world_configuration_artifacts(id, revision_id, game_instance_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (revision_id, game_instance_id)
        REFERENCES world_configuration_revisions(id, game_instance_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS world_configuration_observations_instance_revision_idx
ON world_configuration_observations (game_instance_id, revision_id);

CREATE TABLE IF NOT EXISTS world_configuration_current_revisions (
    game_instance_id uuid PRIMARY KEY REFERENCES game_instances(id) ON DELETE RESTRICT,
    revision_id uuid NOT NULL UNIQUE,
    promoted_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (revision_id, game_instance_id)
        REFERENCES world_configuration_revisions(id, game_instance_id) ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION enforce_world_configuration_lineage()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM game_instances gi
        JOIN game_servers gs ON gs.id = gi.game_server_id
        JOIN provider_resources pr ON pr.id = gs.provider_resource_id
        JOIN provider_connections pc ON pc.id = pr.provider_connection_id
        WHERE gi.id = NEW.game_instance_id
          AND pr.id = NEW.provider_resource_id
          AND pc.id = NEW.provider_connection_id
          AND pc.provider_key = NEW.provider_key
          AND pr.external_resource_id = NEW.external_resource_id
          AND pc.status = 'active'
          AND pr.available = true
    ) THEN
        RAISE EXCEPTION 'Configuration revision provider lineage does not match its game instance'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS world_configuration_revision_lineage_guard
ON world_configuration_revisions;
CREATE TRIGGER world_configuration_revision_lineage_guard
BEFORE INSERT ON world_configuration_revisions
FOR EACH ROW EXECUTE FUNCTION enforce_world_configuration_lineage();

CREATE OR REPLACE FUNCTION enforce_verified_world_configuration_promotion()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM world_configuration_revisions r
        JOIN game_instances gi ON gi.id = r.game_instance_id
        JOIN game_servers gs ON gs.id = gi.game_server_id
        JOIN provider_resources pr ON pr.id = gs.provider_resource_id
        JOIN provider_connections pc ON pc.id = pr.provider_connection_id
        WHERE r.id = NEW.revision_id
          AND r.game_instance_id = NEW.game_instance_id
          AND r.validation_state = 'verified'
          AND r.provider_resource_id = pr.id
          AND r.provider_connection_id = pc.id
          AND r.provider_key = pc.provider_key
          AND r.external_resource_id = pr.external_resource_id
          AND pc.status = 'active'
          AND pr.available = true
    ) THEN
        RAISE EXCEPTION 'Only a verified revision for this game instance may be promoted'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS world_configuration_current_revision_guard
ON world_configuration_current_revisions;
CREATE TRIGGER world_configuration_current_revision_guard
BEFORE INSERT OR UPDATE ON world_configuration_current_revisions
FOR EACH ROW EXECUTE FUNCTION enforce_verified_world_configuration_promotion();

CREATE OR REPLACE FUNCTION prevent_world_configuration_audit_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'World configuration audit records are append-only';
END;
$$;

DROP TRIGGER IF EXISTS world_configuration_revisions_immutable ON world_configuration_revisions;
CREATE TRIGGER world_configuration_revisions_immutable
BEFORE UPDATE OR DELETE ON world_configuration_revisions
FOR EACH ROW EXECUTE FUNCTION prevent_world_configuration_audit_mutation();

DROP TRIGGER IF EXISTS world_configuration_artifacts_immutable ON world_configuration_artifacts;
CREATE TRIGGER world_configuration_artifacts_immutable
BEFORE UPDATE OR DELETE ON world_configuration_artifacts
FOR EACH ROW EXECUTE FUNCTION prevent_world_configuration_audit_mutation();

DROP TRIGGER IF EXISTS world_configuration_observations_immutable ON world_configuration_observations;
CREATE TRIGGER world_configuration_observations_immutable
BEFORE UPDATE OR DELETE ON world_configuration_observations
FOR EACH ROW EXECUTE FUNCTION prevent_world_configuration_audit_mutation();
