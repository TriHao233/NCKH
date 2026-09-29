-- One exam code per exam, and indexes for owner lists, variant lists and the
-- "question edited while used in an open exam" lookup.
CREATE UNIQUE INDEX uq_exam_variant_code ON exam_variants(exam_id, (payload->>'exam_code'));
CREATE INDEX ix_exam_variants_exam_time ON exam_variants(exam_id, created_at);
CREATE INDEX ix_exams_owner_updated ON exams(created_by_user_id, updated_at DESC);
CREATE INDEX ix_exams_updated ON exams(updated_at DESC);
CREATE INDEX ix_exam_questions_question ON exam_questions(question_id);
CREATE INDEX ix_moodle_publications_created ON moodle_publications(created_at DESC);
