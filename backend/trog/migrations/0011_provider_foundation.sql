CREATE TABLE IF NOT EXISTS provider_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    provider_key text NOT NULL,
    display_name text NOT NULL,
    auth_strategy text NOT NULL CHECK (auth_strategy IN ('configuration', 'oauth2')),
    external_account_id text,
    external_account_label text,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'reauthorization_required', 'revoked', 'error')),
    granted_scopes text[] NOT NULL DEFAULT ARRAY[]::text[],
    connected_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    connected_at timestamptz,
    last_verified_at timestamptz,
    revoked_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (provider_key ~ '^[a-z][a-z0-9_]*$'),
    CHECK (external_account_id IS NULL OR length(external_account_id) > 0),
    CHECK (array_position(granted_scopes, NULL) IS NULL),
    UNIQUE (community_id, provider_key, external_account_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_connections_community
ON provider_connections(community_id);

CREATE TABLE IF NOT EXISTS provider_connection_secrets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_connection_id uuid NOT NULL UNIQUE
        REFERENCES provider_connections(id) ON DELETE CASCADE,
    storage_kind text NOT NULL CHECK (storage_kind IN ('external_reference', 'encrypted_payload')),
    secret_reference text,
    encrypted_payload bytea,
    encryption_nonce bytea,
    key_version text,
    expires_at timestamptz,
    rotated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (
            storage_kind = 'external_reference'
            AND secret_reference IS NOT NULL
            AND encrypted_payload IS NULL
            AND encryption_nonce IS NULL
            AND key_version IS NULL
        )
        OR
        (
            storage_kind = 'encrypted_payload'
            AND secret_reference IS NULL
            AND encrypted_payload IS NOT NULL
            AND encryption_nonce IS NOT NULL
            AND key_version IS NOT NULL
        )
    )
);

CREATE TABLE IF NOT EXISTS provider_oauth_states (
    state_hash text PRIMARY KEY,
    provider_key text NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('connect', 'reconnect')),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_connection_id uuid REFERENCES provider_connections(id) ON DELETE CASCADE,
    redirect_path text NOT NULL DEFAULT '/communities/',
    protected_payload bytea,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK (provider_key ~ '^[a-z][a-z0-9_]*$'),
    CHECK (redirect_path LIKE '/%' AND redirect_path NOT LIKE '//%' AND redirect_path !~ '^[a-zA-Z][a-zA-Z0-9+.-]*:'),
    CHECK (
        (purpose = 'connect' AND provider_connection_id IS NULL)
        OR (purpose = 'reconnect' AND provider_connection_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_provider_oauth_states_expiration
ON provider_oauth_states(expires_at)
WHERE consumed_at IS NULL;

CREATE TABLE IF NOT EXISTS provider_resources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_connection_id uuid NOT NULL
        REFERENCES provider_connections(id) ON DELETE CASCADE,
    resource_type text NOT NULL,
    external_resource_id text NOT NULL,
    display_name text NOT NULL,
    provider_game_key text,
    normalized_status text NOT NULL DEFAULT 'unknown'
        CHECK (normalized_status IN ('unknown', 'offline', 'starting', 'degraded', 'online', 'failed')),
    provider_status text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    available boolean NOT NULL DEFAULT true,
    discovered_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz,
    last_status_at timestamptz,
    selected_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (resource_type ~ '^[a-z][a-z0-9_]*$'),
    CHECK (length(external_resource_id) > 0),
    CHECK (jsonb_typeof(metadata) = 'object'),
    UNIQUE (provider_connection_id, resource_type, external_resource_id)
);

CREATE INDEX IF NOT EXISTS idx_provider_resources_connection
ON provider_resources(provider_connection_id);

ALTER TABLE game_servers
ADD COLUMN IF NOT EXISTS provider_resource_id uuid
    REFERENCES provider_resources(id) ON DELETE RESTRICT,
ADD COLUMN IF NOT EXISTS game_key text;

CREATE UNIQUE INDEX IF NOT EXISTS idx_game_servers_provider_resource
ON game_servers(provider_resource_id)
WHERE provider_resource_id IS NOT NULL;

CREATE OR REPLACE FUNCTION enforce_game_server_provider_community()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    resource_community_id uuid;
BEGIN
    IF NEW.provider_resource_id IS NULL THEN
        RETURN NEW;
    END IF;

    SELECT pc.community_id
    INTO resource_community_id
    FROM provider_resources pr
    JOIN provider_connections pc ON pc.id = pr.provider_connection_id
    WHERE pr.id = NEW.provider_resource_id;

    IF resource_community_id IS NULL THEN
        RAISE EXCEPTION 'Provider Resource % does not exist.', NEW.provider_resource_id
            USING ERRCODE = '23503';
    END IF;

    IF resource_community_id <> NEW.community_id THEN
        RAISE EXCEPTION 'Provider Resource % belongs to a different Community.', NEW.provider_resource_id
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS game_servers_provider_community_check ON game_servers;

CREATE TRIGGER game_servers_provider_community_check
BEFORE INSERT OR UPDATE OF community_id, provider_resource_id ON game_servers
FOR EACH ROW
EXECUTE FUNCTION enforce_game_server_provider_community();
