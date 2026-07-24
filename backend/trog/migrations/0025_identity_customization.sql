ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image_url text;
ALTER TABLE communities ADD COLUMN IF NOT EXISTS image_url text;
ALTER TABLE game_instances ADD COLUMN IF NOT EXISTS image_url text;

