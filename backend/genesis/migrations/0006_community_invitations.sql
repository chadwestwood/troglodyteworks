CREATE TABLE IF NOT EXISTS community_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    community_id uuid NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
    invitation_type text NOT NULL CHECK (invitation_type IN ('direct', 'link')),
    invited_user_id uuid REFERENCES users(id) ON DELETE CASCADE,
    token_hash text UNIQUE,
    initial_role text NOT NULL CHECK (initial_role IN ('admin', 'moderator', 'member')),
    requires_approval boolean NOT NULL DEFAULT false,
    maximum_uses integer NOT NULL DEFAULT 1 CHECK (maximum_uses > 0),
    use_count integer NOT NULL DEFAULT 0 CHECK (use_count >= 0),
    expires_at timestamptz,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'revoked', 'expired')),
    created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    revoked_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (
        (invitation_type = 'direct' AND invited_user_id IS NOT NULL AND token_hash IS NULL)
        OR (invitation_type = 'link' AND invited_user_id IS NULL AND token_hash IS NOT NULL)
    ),
    CHECK (use_count <= maximum_uses)
);

CREATE OR REPLACE FUNCTION effective_invitation_status(status text, expires_at timestamptz)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN status = 'pending' AND expires_at IS NOT NULL AND expires_at <= now() THEN 'expired'
        ELSE status
    END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_community_invitations_active_direct
ON community_invitations(community_id, invited_user_id)
WHERE invitation_type = 'direct' AND status = 'pending';

CREATE INDEX IF NOT EXISTS idx_community_invitations_community_status
ON community_invitations(community_id, status);

CREATE INDEX IF NOT EXISTS idx_community_invitations_invited_user
ON community_invitations(invited_user_id)
WHERE invited_user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS community_invitation_redemptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    invitation_id uuid NOT NULL REFERENCES community_invitations(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status text NOT NULL CHECK (status IN ('accepted', 'declined', 'pending_approval', 'approved', 'denied')),
    redeemed_at timestamptz NOT NULL DEFAULT now(),
    approved_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    approved_at timestamptz,
    denied_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    denied_at timestamptz,
    UNIQUE (invitation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_invitation_redemptions_invitation
ON community_invitation_redemptions(invitation_id);

CREATE INDEX IF NOT EXISTS idx_invitation_redemptions_user
ON community_invitation_redemptions(user_id);

CREATE INDEX IF NOT EXISTS idx_invitation_redemptions_pending
ON community_invitation_redemptions(invitation_id, status)
WHERE status = 'pending_approval';
