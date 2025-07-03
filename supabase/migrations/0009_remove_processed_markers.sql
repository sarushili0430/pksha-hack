-- Remove processed_marker records from messages table
-- These are not actual messages but internal tracking records that should not be stored

DELETE FROM messages 
WHERE message_type = 'processed_marker' 
   OR (text_content LIKE 'PROCESSED:%' AND raw_payload->>'marker' = 'true');

-- Add a comment to clarify the purpose of the messages table
COMMENT ON TABLE messages IS 'Stores actual user messages and conversation history. Should not contain system tracking records.';