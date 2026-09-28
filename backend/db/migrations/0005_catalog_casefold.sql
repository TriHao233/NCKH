-- Match the catalog API's case-insensitive code checks under concurrent writes.
CREATE UNIQUE INDEX uq_subject_code_casefold ON subjects (lower(btrim(subject_code)));
CREATE UNIQUE INDEX uq_chapter_code_casefold ON subject_chapters (subject_id, lower(btrim(chapter_code)));
CREATE UNIQUE INDEX uq_clo_code_casefold ON learning_outcomes (subject_id, lower(btrim(clo_code)));
