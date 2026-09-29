-- One editable draft per question and reviewer, even after the question version changes.
ALTER TABLE question_review_drafts ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE question_review_drafts
SET payload = jsonb_build_object(
    'question_id', question_id,
    'question_version_id', question_version_id,
    'reviewer_user_id', reviewer_user_id,
    'draft', draft,
    'created_at', created_at,
    'updated_at', updated_at
);

DO $$
DECLARE old_name text;
BEGIN
    SELECT conname INTO old_name
    FROM pg_constraint
    WHERE conrelid = 'question_review_drafts'::regclass
      AND contype = 'u'
    LIMIT 1;
    IF old_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE question_review_drafts DROP CONSTRAINT %I', old_name);
    END IF;
END $$;

ALTER TABLE question_review_drafts
    ADD CONSTRAINT uq_review_draft_question_reviewer UNIQUE (question_id, reviewer_user_id);
