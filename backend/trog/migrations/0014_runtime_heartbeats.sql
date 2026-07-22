CREATE TABLE IF NOT EXISTS runtime_heartbeats (
    component text PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('ready', 'connecting', 'degraded')),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    checked_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE runtime_heartbeats IS
    'Non-secret liveness signals from long-running TWE runtime components.';
