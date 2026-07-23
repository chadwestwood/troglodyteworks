ALTER TABLE managed_minecraft_hosting_plans
ADD COLUMN IF NOT EXISTS provider_volume_id text,
ADD COLUMN IF NOT EXISTS provider_tcp_proxy_id text,
ADD COLUMN IF NOT EXISTS provider_deployment_id text,
ADD COLUMN IF NOT EXISTS last_error text,
ADD COLUMN IF NOT EXISTS provisioning_started_at timestamptz,
ADD COLUMN IF NOT EXISTS completed_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_managed_minecraft_provider_service
ON managed_minecraft_hosting_plans(provider_service_id)
WHERE provider_service_id IS NOT NULL;

DROP INDEX IF EXISTS uq_managed_minecraft_active_owner;
CREATE UNIQUE INDEX uq_managed_minecraft_active_owner
ON managed_minecraft_hosting_plans(requested_by)
WHERE requested_by IS NOT NULL
  AND (status NOT IN ('cancelled','failed') OR provider_service_id IS NOT NULL);
