-- Extend Contact ticket categories while preserving existing tickets.
ALTER TABLE contact_requests
    DROP CONSTRAINT contact_requests_category_check;

ALTER TABLE contact_requests
    ADD CONSTRAINT contact_requests_category_check
    CHECK (category IN (
        'REVIEW_REQUEST', 'BUG', 'SUPPORT', 'FEEDBACK', 'CONTENT_ISSUE'
    ));
