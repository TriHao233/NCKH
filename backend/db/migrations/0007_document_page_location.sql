-- Non-PDF source units (for example DOCX paragraphs) have no page number.
ALTER TABLE document_pages ALTER COLUMN page_number DROP NOT NULL;
ALTER TABLE document_pages ADD COLUMN unit_number integer;
ALTER TABLE document_pages ADD COLUMN source_location jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE document_pages
SET unit_number = CASE
        WHEN payload->>'unit_number' ~ '^[0-9]+$' THEN (payload->>'unit_number')::integer
        ELSE page_number
    END,
    source_location = CASE
        WHEN jsonb_typeof(payload->'source_location') = 'object'
            THEN payload->'source_location'
        ELSE '{}'::jsonb
    END;

CREATE INDEX ix_document_pages_unit_order
    ON document_pages(document_id, version, unit_number, page_number);
