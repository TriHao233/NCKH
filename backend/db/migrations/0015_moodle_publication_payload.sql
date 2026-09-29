-- Keep the full publication record (target snapshot, mode, attempts) and allow
-- mock publications that were not sent to a configured Moodle target.
ALTER TABLE moodle_publications ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE moodle_publications ALTER COLUMN target_id DROP NOT NULL;

UPDATE moodle_publications
SET payload = jsonb_build_object(
    'question_id', question_id,
    'question_version_id', question_version_id,
    'publisher_user_id', publisher_user_id,
    'idempotency_key', idempotency_key,
    'status', status,
    'request_payload', request_payload,
    'response_payload', response_payload,
    'moodle_question_ref_id', external_ref_id,
    'target', COALESCE(request_payload->'target', '{}'::jsonb),
    'created_at', created_at,
    'updated_at', updated_at
);

CREATE INDEX ix_moodle_publications_question
    ON moodle_publications(question_id, created_at DESC);
CREATE INDEX ix_question_reviews_reviewer_time
    ON question_reviews(reviewer_user_id, reviewed_at DESC);
CREATE INDEX ix_question_reviews_question_time
    ON question_reviews(question_id, reviewed_at DESC);
CREATE INDEX ix_question_evaluations_version_time
    ON question_evaluations(question_version_id, created_at DESC);
