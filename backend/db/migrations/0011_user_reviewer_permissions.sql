-- Reviewer permissions and subject scope must survive the user cutover.
ALTER TABLE users ADD COLUMN permission_grants jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN permission_revokes jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE users ADD COLUMN review_subject_ids jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX ix_users_review_subject_ids ON users USING gin (review_subject_ids);
