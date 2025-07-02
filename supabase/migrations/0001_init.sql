-- 拡張（UUID 生成用）
create extension if not exists "pgcrypto";

------------------------------------------------------------
-- 1. ユーザー（LINE 個人アカウント）
------------------------------------------------------------
create table users (
  id               uuid primary key default gen_random_uuid(),
  line_user_id     text   not null unique,     -- LINE Messaging API の userId
  display_name     text,                       -- get_profile() で取得
  last_profile_sync timestamptz,
  created_at       timestamptz not null default now()
);

create index idx_users_line_user_id on users(line_user_id);

------------------------------------------------------------
-- 2. グループ（LINE グループ／複数人トーク）
------------------------------------------------------------
create table groups (
  id               uuid primary key default gen_random_uuid(),
  line_group_id    text   not null unique,     -- source.groupId
  group_name       text,                       -- getGroupSummary() など
  created_at       timestamptz not null default now()
);

------------------------------------------------------------
-- 3. グループメンバー（多対多）
------------------------------------------------------------
create table group_members (
  group_id         uuid references groups(id) on delete cascade,
  user_id          uuid references users(id)  on delete cascade,
  joined_at        timestamptz not null default now(),
  last_active_at   timestamptz,
  primary key (group_id, user_id)             -- 1人1グループに1行
);

------------------------------------------------------------
-- 4. メッセージログ（任意：デバッグ・分析用）
------------------------------------------------------------
create table messages (
  id               bigserial primary key,
  user_id          uuid references users(id),
  group_id         uuid references groups(id),  -- 1on1 の場合は NULL
  message_type     text,                        -- text / image / sticker …
  text_content     text,
  raw_payload      jsonb,                       -- LINE からの生パケット
  created_at       timestamptz not null default now()
);

create index idx_messages_user_created on messages(user_id, created_at);
create index idx_messages_group_created on messages(group_id, created_at);
