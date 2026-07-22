CREATE TABLE IF NOT EXISTS password_login_failures (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier_hash text NOT NULL CHECK (identifier_hash ~ '^[0-9a-f]{64}$'),
    attempted_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_password_login_failures_identifier_time
ON password_login_failures(identifier_hash, attempted_at DESC);

CREATE INDEX IF NOT EXISTS idx_password_login_failures_attempted_at
ON password_login_failures(attempted_at);
