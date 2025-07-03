-- Create dedicated table for tracking processed messages
-- This prevents duplicate processing without cluttering the messages table

CREATE TABLE processed_messages (
    id bigserial PRIMARY KEY,
    message_id text NOT NULL UNIQUE,
    processed_at timestamptz NOT NULL DEFAULT now(),
    instance_id text -- Optional: to track which instance processed the message
);

-- Index for fast lookup
CREATE INDEX idx_processed_messages_message_id ON processed_messages(message_id);

-- Add TTL cleanup (optional - remove old entries after 7 days)
CREATE INDEX idx_processed_messages_processed_at ON processed_messages(processed_at);

-- Add a comment to clarify the purpose
COMMENT ON TABLE processed_messages IS 'Tracks processed LINE message IDs to prevent duplicate processing across multiple instances';