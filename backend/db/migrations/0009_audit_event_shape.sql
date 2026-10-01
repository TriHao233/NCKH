-- Keep the complete canonical audit event, including actor/entity details and changes.
ALTER TABLE audit_logs ADD COLUMN actor_type text;
ALTER TABLE audit_logs ADD COLUMN actor_role text;
ALTER TABLE audit_logs ADD COLUMN changes jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE audit_logs ADD COLUMN before_hash text;
ALTER TABLE audit_logs ADD COLUMN after_hash text;
ALTER TABLE audit_logs ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE audit_logs
SET actor_type = CASE WHEN actor_user_id IS NULL THEN 'SYSTEM' ELSE 'USER' END,
    actor_role = metadata->>'actor_role',
    payload = jsonb_build_object(
        'action', action,
        'actor', jsonb_build_object(
            'type', CASE WHEN actor_user_id IS NULL THEN 'SYSTEM' ELSE 'USER' END,
            'user_id', actor_user_id,
            'role', metadata->>'actor_role'
        ),
        'entity', jsonb_build_object('type', entity_type, 'id', entity_id),
        'before', before_state,
        'after', after_state,
        'changes', '[]'::jsonb,
        'metadata', metadata,
        'created_at', created_at
    );

CREATE INDEX ix_audit_actor_time ON audit_logs(actor_user_id, created_at DESC);
