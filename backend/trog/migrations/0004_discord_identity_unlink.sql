ALTER TABLE discord_identities
DROP CONSTRAINT IF EXISTS discord_identities_check;

ALTER TABLE discord_identities
ADD CONSTRAINT discord_identities_linked_at_check
CHECK (user_id IS NULL OR linked_at IS NOT NULL);
