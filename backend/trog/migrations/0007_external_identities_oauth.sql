ALTER TABLE users
ALTER COLUMN password_hash DROP NOT NULL;

CREATE TABLE IF NOT EXISTS user_external_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider text NOT NULL CHECK (provider IN ('google', 'discord')),
    provider_subject text NOT NULL,
    provider_username text,
    provider_email text,
    provider_email_verified boolean,
    linked_at timestamptz NOT NULL DEFAULT now(),
    last_authenticated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_subject),
    UNIQUE (user_id, provider),
    CHECK (length(provider_subject) > 0)
);

CREATE INDEX IF NOT EXISTS idx_user_external_identities_user_id
ON user_external_identities(user_id);

CREATE INDEX IF NOT EXISTS idx_user_external_identities_login_lookup
ON user_external_identities(provider, provider_subject);

INSERT INTO user_external_identities
    (user_id, provider, provider_subject, linked_at, created_at, updated_at)
SELECT user_id, 'discord', discord_user_id, linked_at, created_at, updated_at
FROM discord_identities
WHERE user_id IS NOT NULL
  AND linked_at IS NOT NULL
ON CONFLICT (provider, provider_subject) DO NOTHING;

CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash text PRIMARY KEY,
    provider text NOT NULL CHECK (provider IN ('google', 'discord')),
    purpose text NOT NULL CHECK (purpose IN ('login', 'link')),
    user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    redirect_path text NOT NULL DEFAULT '/communities/',
    code_verifier text,
    nonce text,
    nonce_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_at timestamptz,
    CHECK ((purpose = 'login' AND user_id IS NULL) OR (purpose = 'link' AND user_id IS NOT NULL)),
    CHECK (redirect_path LIKE '/%' AND redirect_path NOT LIKE '//%' AND redirect_path !~ '^[a-zA-Z][a-zA-Z0-9+.-]*:')
);

CREATE INDEX IF NOT EXISTS idx_oauth_states_expiration
ON oauth_states(expires_at)
WHERE consumed_at IS NULL;
