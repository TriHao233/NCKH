-- Preserve every subject attached to a document, not only the primary subject.
CREATE TABLE document_subjects (
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    subject_id text NOT NULL REFERENCES subjects(id),
    position_no integer NOT NULL CHECK (position_no >= 0),
    PRIMARY KEY (document_id, subject_id)
);
CREATE INDEX ix_document_subjects_subject ON document_subjects(subject_id, document_id);

-- Backfill existing PostgreSQL shadow copies in the same order as the copy tool.
WITH candidates AS (
    SELECT id AS document_id, subject_id, 0::bigint AS source_order
    FROM documents WHERE subject_id IS NOT NULL
    UNION ALL
    SELECT document.id, candidate.subject_id, candidate.ordinality
    FROM documents AS document
    CROSS JOIN LATERAL jsonb_array_elements_text(
        CASE WHEN jsonb_typeof(document.payload->'subject_ids') = 'array'
             THEN document.payload->'subject_ids' ELSE '[]'::jsonb END
    ) WITH ORDINALITY AS candidate(subject_id, ordinality)
), ordered AS (
    SELECT candidates.document_id, candidates.subject_id, min(source_order) AS source_order
    FROM candidates JOIN subjects ON subjects.id = candidates.subject_id
    GROUP BY candidates.document_id, candidates.subject_id
)
INSERT INTO document_subjects (document_id, subject_id, position_no)
SELECT document_id, subject_id,
       (row_number() OVER (PARTITION BY document_id ORDER BY source_order, subject_id) - 1)::integer
FROM ordered;
