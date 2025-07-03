-- Questions and Question Targets System
-- This migration creates tables for tracking questions and their targets

------------------------------------------------------------
-- 1. Questions table - store question metadata
------------------------------------------------------------
create table questions (
  id                uuid primary key default gen_random_uuid(),
  group_id          uuid references groups(id) on delete cascade,
  questioner_user_id uuid references users(id) on delete cascade,
  question_text     text not null,
  message_id        text,                        -- LINE message ID for reference
  remind_at         timestamptz not null,        -- when to send reminder
  resolved_at       timestamptz,                 -- when question was resolved
  created_at        timestamptz not null default now()
);

create index idx_questions_group_id on questions(group_id);
create index idx_questions_questioner on questions(questioner_user_id);
create index idx_questions_remind_at on questions(remind_at);
create index idx_questions_resolved on questions(resolved_at);

------------------------------------------------------------
-- 2. Question Targets table - store who should respond (1-to-many)
------------------------------------------------------------
create table question_targets (
  id              uuid primary key default gen_random_uuid(),
  question_id     uuid references questions(id) on delete cascade,
  target_user_id  uuid references users(id) on delete cascade,
  responded_at    timestamptz,                  -- when target responded
  created_at      timestamptz not null default now()
);

create index idx_question_targets_question_id on question_targets(question_id);
create index idx_question_targets_user_id on question_targets(target_user_id);
create index idx_question_targets_responded on question_targets(responded_at);

-- Unique constraint to prevent duplicate targets for same question
create unique index idx_question_targets_unique on question_targets(question_id, target_user_id);