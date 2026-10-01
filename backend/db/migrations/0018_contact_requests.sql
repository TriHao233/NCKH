-- Internal contact / support tickets: Teacher → Admin.
-- Ticket status flow: NEW → IN_PROGRESS → RESOLVED → CLOSED.
-- Categories: BUG, SUPPORT, FEEDBACK.

CREATE TABLE contact_requests (
    id text PRIMARY KEY,
    ticket_code text NOT NULL UNIQUE,
    user_id text NOT NULL REFERENCES users(id),
    category text NOT NULL CHECK (category IN ('BUG', 'SUPPORT', 'FEEDBACK')),
    title text NOT NULL,
    content text NOT NULL,
    status text NOT NULL DEFAULT 'NEW'
        CHECK (status IN ('NEW', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    resolved_at timestamptz
);

CREATE INDEX ix_contact_requests_user ON contact_requests(user_id, created_at DESC);
CREATE INDEX ix_contact_requests_status ON contact_requests(status, updated_at DESC);

CREATE TABLE contact_messages (
    id text PRIMARY KEY,
    request_id text NOT NULL REFERENCES contact_requests(id) ON DELETE CASCADE,
    sender_id text NOT NULL REFERENCES users(id),
    message text NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_contact_messages_request ON contact_messages(request_id, created_at);
