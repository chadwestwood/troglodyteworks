ALTER TABLE discord_guild_installations
ADD COLUMN IF NOT EXISTS personality_preset text NOT NULL DEFAULT 'friendly';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE con.conname = 'discord_guild_installations_personality_preset_check'
          AND rel.relname = 'discord_guild_installations'
    ) THEN
        ALTER TABLE discord_guild_installations
        ADD CONSTRAINT discord_guild_installations_personality_preset_check
        CHECK (
            personality_preset IN (
                'friendly',
                'direct',
                'sarcastic',
                'professional',
                'enthusiastic'
            )
        );
    END IF;
END $$;
