-- Scenario B business schema. IDs remain the existing 24-character ObjectId
-- strings during migration so API responses and cross-store references survive.
-- JSONB payloads retain historical fields while indexed business keys are
-- promoted to typed columns. No foreign key points into MongoDB or ChromaDB.

CREATE TABLE users (
    id text PRIMARY KEY,
    firebase_uid text NOT NULL UNIQUE,
    email text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('Admin', 'Teacher', 'Reviewer')),
    permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    profile jsonb NOT NULL DEFAULT '{}'::jsonb,
    generation_presets jsonb NOT NULL DEFAULT '[]'::jsonb,
    task_calendar jsonb NOT NULL DEFAULT '[]'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));
CREATE INDEX ix_users_role_active ON users (role, is_active);

CREATE TABLE user_sessions (
    firebase_uid text PRIMARY KEY REFERENCES users(firebase_uid) ON DELETE CASCADE,
    demo_token_hash text,
    revoked_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE subjects (
    id text PRIMARY KEY,
    subject_code text NOT NULL UNIQUE,
    subject_name text NOT NULL,
    owner_id text REFERENCES users(id),
    is_active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE subject_chapters (
    id text PRIMARY KEY,
    subject_id text NOT NULL REFERENCES subjects(id),
    chapter_code text NOT NULL,
    chapter_name text NOT NULL,
    sequence_no integer NOT NULL DEFAULT 1,
    is_active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (subject_id, chapter_code)
);
CREATE TABLE learning_outcomes (
    id text PRIMARY KEY,
    subject_id text NOT NULL REFERENCES subjects(id),
    clo_code text NOT NULL,
    description text NOT NULL,
    target_weight numeric(8,6) NOT NULL DEFAULT 1,
    is_active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (subject_id, clo_code)
);
CREATE TABLE keywords (
    id text PRIMARY KEY,
    subject_id text REFERENCES subjects(id),
    keyword text NOT NULL,
    status text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE ai_models (
    id text PRIMARY KEY,
    model_code text NOT NULL UNIQUE,
    display_name text NOT NULL,
    runtime text NOT NULL,
    capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
    priority integer NOT NULL DEFAULT 10,
    is_active boolean NOT NULL DEFAULT true,
    active_version_id text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE ai_model_versions (
    id text PRIMARY KEY,
    model_id text NOT NULL REFERENCES ai_models(id),
    version integer NOT NULL CHECK (version > 0),
    model_name text NOT NULL,
    revision text,
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
    endpoint_alias text,
    secret_ref text,
    config_hash text NOT NULL,
    created_by_user_id text REFERENCES users(id),
    created_at timestamptz NOT NULL,
    UNIQUE (model_id, version)
);
ALTER TABLE ai_models ADD CONSTRAINT fk_ai_model_active_version
    FOREIGN KEY (active_version_id) REFERENCES ai_model_versions(id)
    DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE prompt_templates (
    id text PRIMARY KEY,
    template_key text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    kind text NOT NULL,
    name text NOT NULL,
    prompt_body text NOT NULL,
    content_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT false,
    created_by_user_id text REFERENCES users(id),
    created_at timestamptz NOT NULL,
    UNIQUE (template_key, version)
);
CREATE UNIQUE INDEX uq_active_prompt ON prompt_templates(template_key) WHERE is_active;
CREATE TABLE evaluation_policies (
    id text PRIMARY KEY,
    policy_name text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    weights jsonb NOT NULL,
    thresholds jsonb NOT NULL,
    weights_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT false,
    created_by_user_id text REFERENCES users(id),
    created_at timestamptz NOT NULL,
    UNIQUE (policy_name, version)
);
CREATE UNIQUE INDEX uq_active_policy ON evaluation_policies(policy_name) WHERE is_active;

CREATE TABLE documents (
    id text PRIMARY KEY,
    title text NOT NULL,
    original_filename text NOT NULL,
    subject_id text REFERENCES subjects(id),
    uploaded_by_user_id text REFERENCES users(id),
    status text NOT NULL,
    current_version integer NOT NULL DEFAULT 1,
    active_chunk_set_id text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX ix_documents_owner_status ON documents(uploaded_by_user_id, status);
CREATE TABLE document_artifacts (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id),
    artifact_type text NOT NULL,
    storage_provider text NOT NULL,
    storage_key text NOT NULL,
    checksum_sha256 text,
    mime_type text,
    size_bytes bigint,
    version integer NOT NULL DEFAULT 1,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);
CREATE TABLE document_jobs (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id),
    job_type text NOT NULL,
    status text NOT NULL,
    attempt_no integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX ix_document_jobs_queue ON document_jobs(status, created_at);
CREATE TABLE document_pages (
    id text PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id),
    ocr_job_id text REFERENCES document_jobs(id),
    page_number integer NOT NULL,
    raw_text text,
    clean_text text,
    version integer NOT NULL DEFAULT 1,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX ix_document_pages_document_order ON document_pages(document_id, page_number);

CREATE TABLE questions (
    id text PRIMARY KEY,
    question_code text NOT NULL UNIQUE,
    subject_id text REFERENCES subjects(id),
    created_by_user_id text REFERENCES users(id),
    current_version integer NOT NULL CHECK (current_version > 0),
    current_version_id text,
    approved_version_id text,
    lifecycle_status text NOT NULL,
    review_status text NOT NULL,
    evaluation_status text NOT NULL,
    publication_status text NOT NULL,
    assignment jsonb NOT NULL DEFAULT '{}'::jsonb,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX ix_questions_review_queue ON questions(review_status, updated_at)
    WHERE lifecycle_status = 'ACTIVE';
CREATE INDEX ix_questions_owner_subject ON questions(created_by_user_id, subject_id)
    WHERE lifecycle_status = 'ACTIVE';
CREATE TABLE question_versions (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id) DEFERRABLE INITIALLY DEFERRED,
    version integer NOT NULL CHECK (version > 0),
    origin text NOT NULL,
    content text NOT NULL,
    question_data jsonb NOT NULL,
    classification jsonb NOT NULL DEFAULT '{}'::jsonb,
    clos jsonb NOT NULL DEFAULT '[]'::jsonb,
    sources jsonb NOT NULL DEFAULT '[]'::jsonb,
    content_hash text NOT NULL,
    created_by_user_id text REFERENCES users(id),
    generation_run_id text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    UNIQUE (question_id, version),
    UNIQUE (question_id, id)
);
ALTER TABLE questions ADD CONSTRAINT fk_question_current_version
    FOREIGN KEY (id, current_version_id) REFERENCES question_versions(question_id, id)
    DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE questions ADD CONSTRAINT fk_question_approved_version
    FOREIGN KEY (id, approved_version_id) REFERENCES question_versions(question_id, id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE generation_jobs (
    id text PRIMARY KEY,
    requested_by_user_id text REFERENCES users(id),
    idempotency_key text,
    status text NOT NULL,
    request jsonb NOT NULL,
    model_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    metrics jsonb,
    attempt_no integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    next_attempt_at timestamptz,
    error_message text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE UNIQUE INDEX uq_generation_idempotency ON generation_jobs(requested_by_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX ix_generation_jobs_queue ON generation_jobs(status, next_attempt_at, created_at);
CREATE TABLE generation_runs (
    id text PRIMARY KEY,
    generation_job_id text REFERENCES generation_jobs(id),
    document_id text REFERENCES documents(id),
    requested_by_user_id text REFERENCES users(id),
    model_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    prompt_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    retrieval_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    result jsonb,
    metrics jsonb,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
ALTER TABLE question_versions ADD CONSTRAINT fk_question_generation_run
    FOREIGN KEY (generation_run_id) REFERENCES generation_runs(id)
    DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE evaluation_jobs (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    requested_by_user_id text REFERENCES users(id),
    status text NOT NULL,
    evaluator_model_code text NOT NULL,
    model_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
    result jsonb,
    attempt_no integer NOT NULL DEFAULT 0,
    lease_owner text,
    lease_expires_at timestamptz,
    next_attempt_at timestamptz,
    error jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE INDEX ix_evaluation_jobs_queue ON evaluation_jobs(status, next_attempt_at, created_at);
CREATE TABLE question_evaluations (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    evaluation_job_id text REFERENCES evaluation_jobs(id),
    result jsonb NOT NULL,
    model_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);
CREATE TABLE question_reviews (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    reviewer_user_id text REFERENCES users(id),
    decision text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz NOT NULL
);
CREATE TABLE question_review_drafts (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    reviewer_user_id text NOT NULL REFERENCES users(id),
    draft jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (question_version_id, reviewer_user_id)
);
CREATE TABLE question_comments (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    author_user_id text NOT NULL REFERENCES users(id),
    body text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    deleted_at timestamptz
);
CREATE INDEX ix_question_comments_thread ON question_comments(question_id, created_at);

CREATE TABLE exams (
    id text PRIMARY KEY,
    created_by_user_id text REFERENCES users(id),
    subject_id text REFERENCES subjects(id),
    status text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE exam_questions (
    exam_id text NOT NULL REFERENCES exams(id),
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    position integer NOT NULL,
    snapshot jsonb NOT NULL,
    PRIMARY KEY (exam_id, position)
);
CREATE TABLE exam_variants (
    id text PRIMARY KEY,
    exam_id text NOT NULL REFERENCES exams(id),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE llm_slots (
    provider text NOT NULL,
    slot_index integer NOT NULL,
    holder_id text,
    lease_expires_at timestamptz,
    updated_at timestamptz NOT NULL,
    PRIMARY KEY (provider, slot_index)
);
CREATE TABLE notifications (
    id text PRIMARY KEY,
    recipient_user_id text NOT NULL REFERENCES users(id),
    kind text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    read_at timestamptz,
    created_at timestamptz NOT NULL
);
CREATE INDEX ix_notifications_unread ON notifications(recipient_user_id, created_at DESC)
    WHERE read_at IS NULL;
CREATE TABLE audit_logs (
    id text PRIMARY KEY,
    actor_user_id text REFERENCES users(id),
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    before_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_state jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);
CREATE INDEX ix_audit_entity ON audit_logs(entity_type, entity_id, created_at DESC);
CREATE TABLE moodle_targets (
    id text PRIMARY KEY,
    site_key text NOT NULL UNIQUE,
    site_name text NOT NULL,
    mode text NOT NULL,
    secret_ref text,
    is_active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE moodle_publications (
    id text PRIMARY KEY,
    question_id text NOT NULL REFERENCES questions(id),
    question_version_id text NOT NULL REFERENCES question_versions(id),
    target_id text NOT NULL REFERENCES moodle_targets(id),
    publisher_user_id text REFERENCES users(id),
    idempotency_key text NOT NULL UNIQUE,
    status text NOT NULL,
    request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    response_payload jsonb,
    external_ref_id text,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
CREATE TABLE outbox_events (
    id text PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    event_type text NOT NULL,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'PENDING',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_owner text,
    lease_expires_at timestamptz,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_outbox_queue ON outbox_events(status, next_attempt_at, created_at);
