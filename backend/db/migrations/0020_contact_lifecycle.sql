-- Reversible Contact deletion and an auditable request lifecycle.
ALTER TABLE contact_requests
    DROP CONSTRAINT contact_requests_status_check;

ALTER TABLE contact_requests
    ADD CONSTRAINT contact_requests_status_check
    CHECK (status IN ('NEW', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'WITHDRAWN'));

ALTER TABLE contact_requests
    ADD COLUMN withdrawn_at timestamptz,
    ADD COLUMN deleted_at timestamptz,
    ADD COLUMN deleted_by text REFERENCES users(id);

CREATE INDEX ix_contact_requests_deleted ON contact_requests(deleted_at, updated_at DESC);

CREATE TABLE contact_request_events (
    id text PRIMARY KEY,
    request_id text NOT NULL REFERENCES contact_requests(id),
    actor_id text NOT NULL REFERENCES users(id),
    action text NOT NULL CHECK (action IN ('EDITED', 'RECLASSIFIED', 'WITHDRAWN', 'DELETED', 'RESTORED')),
    old_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    new_value jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);

CREATE INDEX ix_contact_request_events_request
    ON contact_request_events(request_id, created_at, id);
