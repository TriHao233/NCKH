-- One normalized keyword per legacy dictionary/course across CORE, LEARNED and PENDING.
-- Subject keywords without course_id retain their existing behavior.
CREATE UNIQUE INDEX uq_dictionary_course_keyword
    ON keywords ((payload->>'course_id'), lower(btrim(keyword)))
    WHERE payload ? 'course_id';
