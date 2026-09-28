CREATE TABLE review_settings (
    id text PRIMARY KEY,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_by_user_id text REFERENCES users(id),
    updated_at timestamptz NOT NULL
);
