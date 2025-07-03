-- Add reminded_at column to question_targets table
-- This column tracks when a reminder was sent to each individual target

alter table question_targets add column reminded_at timestamptz;

-- Add index for efficient querying
create index idx_question_targets_reminded_at on question_targets(reminded_at);