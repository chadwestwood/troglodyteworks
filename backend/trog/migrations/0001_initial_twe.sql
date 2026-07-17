CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_activity_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active_token ON sessions(session_token_hash)
WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS communities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    slug text NOT NULL UNIQUE,
    description text,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS community_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner', 'admin', 'moderator', 'member')),
    joined_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, community_id)
);

CREATE INDEX IF NOT EXISTS idx_memberships_user_id ON community_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_memberships_community_id ON community_memberships(community_id);

CREATE TABLE IF NOT EXISTS game_servers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    name text NOT NULL,
    slug text NOT NULL,
    game_type text NOT NULL,
    management_adapter text NOT NULL,
    status text NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown', 'offline', 'starting', 'degraded', 'online', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (community_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_game_servers_community_id ON game_servers(community_id);

CREATE TABLE IF NOT EXISTS game_instances (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_server_id uuid NOT NULL REFERENCES game_servers(id) ON DELETE CASCADE,
    name text NOT NULL,
    slug text NOT NULL,
    instance_type text NOT NULL,
    game_identifier text NOT NULL,
    status text NOT NULL DEFAULT 'unknown' CHECK (status IN ('unknown', 'offline', 'starting', 'degraded', 'online', 'failed')),
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (game_server_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_game_instances_game_server_id ON game_instances(game_server_id);

CREATE TABLE IF NOT EXISTS server_operations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    game_instance_id uuid NOT NULL REFERENCES game_instances(id) ON DELETE CASCADE,
    requested_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    capability text NOT NULL,
    status text NOT NULL CHECK (status IN ('requested', 'queued', 'executing', 'verifying', 'completed', 'failed', 'cancelled')),
    current_stage text,
    requested_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    result_message text
);

CREATE INDEX IF NOT EXISTS idx_server_operations_instance_id ON server_operations(game_instance_id);
CREATE INDEX IF NOT EXISTS idx_server_operations_requested_by ON server_operations(requested_by);
CREATE INDEX IF NOT EXISTS idx_server_operations_active ON server_operations(game_instance_id, capability, status)
WHERE status IN ('requested', 'queued', 'executing', 'verifying');

CREATE TABLE IF NOT EXISTS server_operation_checks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    server_operation_id uuid NOT NULL REFERENCES server_operations(id) ON DELETE CASCADE,
    name text NOT NULL,
    status text NOT NULL CHECK (status IN ('pending', 'running', 'passed', 'failed', 'skipped')),
    started_at timestamptz,
    completed_at timestamptz,
    result_message text,
    sort_order integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_operation_checks_operation_id ON server_operation_checks(server_operation_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    community_id uuid REFERENCES communities(id) ON DELETE SET NULL,
    action text NOT NULL,
    target_type text NOT NULL,
    target_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    details jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_community_id ON audit_logs(community_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
