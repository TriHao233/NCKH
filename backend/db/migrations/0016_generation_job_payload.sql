-- Keep the full generation job (fallback/code model snapshots, progress, retry
-- and dead-letter fields) so the worker queue can run from PostgreSQL.
ALTER TABLE generation_jobs ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE generation_jobs
SET payload = jsonb_build_object(
    'requested_by_user_id', requested_by_user_id,
    'idempotency_key', idempotency_key,
    'status', status,
    'request', request,
    'model_snapshot', model_snapshot,
    'result', result,
    'metrics', metrics,
    'attempt_count', attempt_no,
    'lease_expires_at', lease_expires_at,
    'next_attempt_at', next_attempt_at,
    'error_message', error_message,
    'created_at', created_at,
    'updated_at', updated_at
);

CREATE INDEX ix_generation_jobs_requester
    ON generation_jobs(requested_by_user_id, created_at DESC);
CREATE INDEX ix_generation_jobs_updated ON generation_jobs(updated_at DESC);
CREATE INDEX ix_generation_runs_document ON generation_runs(document_id, created_at DESC);
CREATE INDEX ix_generation_runs_created ON generation_runs(created_at DESC);
