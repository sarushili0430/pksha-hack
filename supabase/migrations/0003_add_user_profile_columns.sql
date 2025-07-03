-- Add additional columns to users table for LINE profile information
alter table users
add column if not exists picture_url text,
add column if not exists status_message text,
add column if not exists language text;