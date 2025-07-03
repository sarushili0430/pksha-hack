-- LINE Group Cache table
-- This table caches LINE group information to reduce API calls

create table line_group_cache (
  line_group_id text primary key,
  group_name text,
  picture_url text,
  updated_at timestamptz not null default now()
);

-- Add index for efficient querying
create index idx_line_group_cache_updated_at on line_group_cache(updated_at);