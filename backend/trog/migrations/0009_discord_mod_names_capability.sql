DO $$
DECLARE
    old_constraint text;
BEGIN
    SELECT con.conname
    INTO old_constraint
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'discord_instance_access_grant_capabilities'
      AND con.contype = 'c'
      AND pg_get_constraintdef(con.oid) LIKE '%instance.players.names.read%';

    IF old_constraint IS NOT NULL THEN
        EXECUTE format(
            'ALTER TABLE discord_instance_access_grant_capabilities DROP CONSTRAINT %I',
            old_constraint
        );
    END IF;
END $$;

ALTER TABLE discord_instance_access_grant_capabilities
ADD CONSTRAINT discord_instance_access_grant_capability_check CHECK (
    capability IN (
        'instance.status.read',
        'instance.players.count.read',
        'instance.players.names.read',
        'instance.mods.names.read'
    )
);

INSERT INTO discord_instance_access_grant_capabilities
    (discord_instance_access_grant_id, capability, granted_by)
SELECT diag.id, 'instance.mods.names.read', diag.provider_approved_by
FROM discord_instance_access_grants diag
WHERE diag.provider_approved_at IS NOT NULL
  AND (
      SELECT count(DISTINCT cap.capability)
      FROM discord_instance_access_grant_capabilities cap
      WHERE cap.discord_instance_access_grant_id = diag.id
        AND cap.revoked_at IS NULL
        AND cap.capability IN (
            'instance.status.read',
            'instance.players.count.read',
            'instance.players.names.read'
        )
  ) = 3
  AND NOT EXISTS (
      SELECT 1
      FROM discord_instance_access_grant_capabilities existing
      WHERE existing.discord_instance_access_grant_id = diag.id
        AND existing.capability = 'instance.mods.names.read'
        AND existing.revoked_at IS NULL
  );
