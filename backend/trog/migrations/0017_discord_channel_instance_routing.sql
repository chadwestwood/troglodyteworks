-- A Discord installation can expose several hosted game instances when each
-- grant is routed by channel. Resolution remains fail-closed if routes overlap.
DROP INDEX IF EXISTS idx_discord_instance_access_one_active_installation;

CREATE INDEX IF NOT EXISTS idx_discord_instance_access_active_installation
ON discord_instance_access_grants(discord_guild_installation_id)
WHERE status = 'active';
