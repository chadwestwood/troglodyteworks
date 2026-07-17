ALTER TABLE game_servers
ADD CONSTRAINT game_servers_id_community_id_unique UNIQUE (id, community_id);

ALTER TABLE game_instances
ADD CONSTRAINT game_instances_id_game_server_id_unique UNIQUE (id, game_server_id);

CREATE TABLE IF NOT EXISTS discord_instance_access_grants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_guild_installation_id uuid REFERENCES discord_guild_installations(id) ON DELETE CASCADE,
    provider_community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    game_server_id uuid NOT NULL REFERENCES game_servers(id) ON DELETE CASCADE,
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE CASCADE,
    requested_by uuid REFERENCES users(id) ON DELETE SET NULL,
    requester_discord_user_id text CHECK (requester_discord_user_id IS NULL OR requester_discord_user_id ~ '^[0-9]+$'),
    consumer_discord_guild_id text CHECK (consumer_discord_guild_id IS NULL OR consumer_discord_guild_id ~ '^[0-9]+$'),
    consumer_discord_guild_name text,
    status text NOT NULL DEFAULT 'pending_discord_verification' CHECK (
        status IN (
            'pending_discord_verification',
            'pending_provider_approval',
            'pending_bot_installation',
            'active',
            'denied',
            'revoked',
            'configuration_error'
        )
    ),
    channel_scope text NOT NULL DEFAULT 'all' CHECK (channel_scope IN ('all', 'allowlist')),
    provider_approved_by uuid REFERENCES users(id) ON DELETE SET NULL,
    provider_approved_at timestamptz,
    discord_approved_by uuid REFERENCES users(id) ON DELETE SET NULL,
    discord_approver_user_id text CHECK (discord_approver_user_id IS NULL OR discord_approver_user_id ~ '^[0-9]+$'),
    discord_approved_at timestamptz,
    installed_at timestamptz,
    activated_at timestamptz,
    denied_by uuid REFERENCES users(id) ON DELETE SET NULL,
    denied_at timestamptz,
    revoked_by uuid REFERENCES users(id) ON DELETE SET NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (requester_discord_user_id IS NULL OR length(requester_discord_user_id) BETWEEN 1 AND 20),
    CHECK (consumer_discord_guild_id IS NULL OR length(consumer_discord_guild_id) BETWEEN 1 AND 20),
    CHECK (discord_approver_user_id IS NULL OR length(discord_approver_user_id) BETWEEN 1 AND 20),
    CHECK (
        status <> 'active'
        OR (
            discord_guild_installation_id IS NOT NULL
            AND consumer_discord_guild_id IS NOT NULL
            AND provider_approved_at IS NOT NULL
            AND discord_approved_at IS NOT NULL
            AND installed_at IS NOT NULL
            AND activated_at IS NOT NULL
            AND denied_at IS NULL
            AND revoked_at IS NULL
        )
    ),
    CHECK (status <> 'denied' OR denied_at IS NOT NULL),
    CHECK (status <> 'revoked' OR revoked_at IS NOT NULL),
    FOREIGN KEY (game_server_id, provider_community_id)
        REFERENCES game_servers(id, community_id) ON DELETE CASCADE,
    FOREIGN KEY (game_instance_id, game_server_id)
        REFERENCES game_instances(id, game_server_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_instance_access_one_active_installation
ON discord_instance_access_grants(discord_guild_installation_id)
WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_discord_instance_access_provider
ON discord_instance_access_grants(provider_community_id);

CREATE INDEX IF NOT EXISTS idx_discord_instance_access_instance
ON discord_instance_access_grants(game_instance_id);

CREATE INDEX IF NOT EXISTS idx_discord_instance_access_guild_status
ON discord_instance_access_grants(consumer_discord_guild_id, status);

CREATE TABLE IF NOT EXISTS discord_instance_access_grant_capabilities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    discord_instance_access_grant_id uuid NOT NULL REFERENCES discord_instance_access_grants(id) ON DELETE CASCADE,
    capability text NOT NULL CHECK (
        capability IN (
            'instance.status.read',
            'instance.players.count.read',
            'instance.players.names.read'
        )
    ),
    granted_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_discord_instance_access_active_capability
ON discord_instance_access_grant_capabilities(discord_instance_access_grant_id, capability)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_discord_instance_access_capabilities_grant
ON discord_instance_access_grant_capabilities(discord_instance_access_grant_id);

CREATE TABLE IF NOT EXISTS discord_oauth_states (
    state text PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    grant_id uuid REFERENCES discord_instance_access_grants(id) ON DELETE CASCADE,
    purpose text NOT NULL CHECK (purpose IN ('guild_verification', 'bot_install')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_discord_oauth_states_user_id
ON discord_oauth_states(user_id);

CREATE TABLE IF NOT EXISTS discord_guild_authority_verifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    discord_user_id text NOT NULL CHECK (discord_user_id ~ '^[0-9]+$'),
    discord_guild_id text NOT NULL CHECK (discord_guild_id ~ '^[0-9]+$'),
    discord_guild_name text,
    can_manage_guild boolean NOT NULL DEFAULT false,
    authority_source text NOT NULL CHECK (authority_source IN ('owner', 'administrator', 'manage_guild')),
    verified_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (length(discord_user_id) BETWEEN 1 AND 20),
    CHECK (length(discord_guild_id) BETWEEN 1 AND 20),
    UNIQUE (user_id, discord_guild_id)
);

CREATE INDEX IF NOT EXISTS idx_discord_guild_authority_lookup
ON discord_guild_authority_verifications(user_id, discord_guild_id, expires_at);
