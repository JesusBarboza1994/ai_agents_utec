-- Customers: one row per person we've talked to on any channel, keyed by
-- the same chat_key used to identify their chat.
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY,
    chat_key TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    phone TEXT,
    -- Room for whatever else gets collected later without a new migration per field.
    extra JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

-- Chats: the main table. One thread per chat_key, linked to its customer.
-- channel_number is the business's own WhatsApp address (Twilio's `To`):
-- which number the customer wrote to, for when there's more than one.
CREATE TABLE IF NOT EXISTS chats (
    id TEXT PRIMARY KEY,
    chat_key TEXT NOT NULL UNIQUE,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    channel TEXT NOT NULL DEFAULT 'whatsapp',
    channel_number TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    last_message_at TIMESTAMPTZ NOT NULL
);

-- Messages: every turn of a chat. There is no stored "session" row -- the
-- 7-day window the LLM sees is a runtime filter on created_at, not a table
-- (see messages_repository.get_recent_messages). provider_message_id is
-- Twilio's MessageSid, kept for future dedup against webhook retries.
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    provider_message_id TEXT,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_chat_created ON messages (chat_id, created_at);
