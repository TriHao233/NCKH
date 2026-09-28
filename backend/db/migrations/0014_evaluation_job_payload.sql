ALTER TABLE evaluation_jobs ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE evaluation_jobs
SET payload = jsonb_build_object(
    'question_id', question_id,
    'question_version_id', question_version_id,
    'requested_by_user_id', requested_by_user_id,
    'status', status,
    'evaluator_model_code', evaluator_model_code,
    'model_snapshot', model_snapshot,
    'policy_snapshot', policy_snapshot,
    'source_snapshot', source_snapshot,
    'result', result,
    'attempt_no', attempt_no,
    'lease_expires_at', lease_expires_at,
    'next_attempt_at', next_attempt_at,
    'error', error,
    'created_at', created_at,
    'updated_at', updated_at
);

CREATE UNIQUE INDEX uq_active_evaluation_dedupe
    ON evaluation_jobs ((payload->>'dedupe_key'))
    WHERE payload->>'dedupe_key' IS NOT NULL
      AND status IN ('QUEUED', 'PROCESSING');
