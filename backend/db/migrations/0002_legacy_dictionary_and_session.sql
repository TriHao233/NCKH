-- Preserve legacy dictionaries during the transition; normalized keywords can
-- be queried by course_id without losing the original dictionary snapshot.
CREATE TABLE legacy_dictionaries (
    id text PRIMARY KEY,
    course_id text NOT NULL UNIQUE,
    name text,
    category text,
    is_active boolean NOT NULL DEFAULT true,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

-- Firebase UID can change when a legacy account is linked by verified email.
ALTER TABLE user_sessions DROP CONSTRAINT user_sessions_firebase_uid_fkey;
ALTER TABLE user_sessions ADD CONSTRAINT user_sessions_firebase_uid_fkey
    FOREIGN KEY (firebase_uid) REFERENCES users(firebase_uid)
    ON UPDATE CASCADE ON DELETE CASCADE;
