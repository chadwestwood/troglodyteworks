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
      AND pg_get_constraintdef(con.oid) LIKE '%instance.mods.names.read%';

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
        'instance.mods.names.read',
        'instance.mods.write',
        'instance.restart.execute'
    )
);

-- Administrative capabilities are intentionally not granted by default.
-- A provider Community owner can operate their own instance; delegated
-- administrators require an explicit, revocable capability grant.
