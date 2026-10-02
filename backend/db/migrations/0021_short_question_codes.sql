-- Human-readable codes are independent of the internal question IDs.
-- Sequence allocation remains atomic across API and generation worker processes.
CREATE SEQUENCE question_code_seq AS bigint START WITH 1;

SELECT setval(
    'question_code_seq',
    COALESCE((
        SELECT max(substring(question_code FROM 3)::bigint)
        FROM questions
        WHERE question_code ~ '^Q-[0-9]{1,18}$'
    ), 0) + 1,
    false
);
