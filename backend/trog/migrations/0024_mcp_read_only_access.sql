CREATE TABLE IF NOT EXISTS mcp_access_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    token_prefix text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    last_used_at timestamptz,
    revoked_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_mcp_access_tokens_user_id
ON mcp_access_tokens(user_id);

CREATE INDEX IF NOT EXISTS idx_mcp_access_tokens_active_hash
ON mcp_access_tokens(token_hash)
WHERE revoked_at IS NULL;

