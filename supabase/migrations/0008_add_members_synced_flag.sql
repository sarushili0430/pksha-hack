-- Add members_synced flag to groups table
-- This flag indicates whether group members have been synced from LINE API

ALTER TABLE groups ADD COLUMN members_synced boolean DEFAULT false;

-- Add index for performance
CREATE INDEX idx_groups_members_synced ON groups(members_synced);

-- Update existing groups to have the flag as false (need to sync)
UPDATE groups SET members_synced = false WHERE members_synced IS NULL;