-- Business decisions about the active document lineage belong with documents.
CREATE TABLE document_lineage_events (
    operation_id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id),
    event_type text NOT NULL,
    actor text NOT NULL,
    reason text NOT NULL,
    from_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    to_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation jsonb NOT NULL DEFAULT '{}'::jsonb,
    rollback_available boolean NOT NULL DEFAULT false,
    promotion_operation_id text REFERENCES document_lineage_events(operation_id)
        DEFERRABLE INITIALLY DEFERRED,
    status text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_document_lineage_events_document
    ON document_lineage_events(document_id, created_at DESC);
