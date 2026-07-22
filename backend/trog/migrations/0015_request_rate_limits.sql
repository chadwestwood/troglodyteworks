CREATE TABLE IF NOT EXISTS request_rate_limits (
    scope text NOT NULL,
    identifier_hash text NOT NULL,
    window_started_at timestamptz NOT NULL,
    request_count integer NOT NULL CHECK (request_count > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, identifier_hash)
);

CREATE INDEX IF NOT EXISTS request_rate_limits_updated_at_idx
    ON request_rate_limits (updated_at);
