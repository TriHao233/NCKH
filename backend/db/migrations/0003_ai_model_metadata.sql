ALTER TABLE ai_models ADD COLUMN description text NOT NULL DEFAULT '';
ALTER TABLE ai_models ADD COLUMN is_local boolean NOT NULL DEFAULT true;
ALTER TABLE ai_models ADD COLUMN last_health_check jsonb;

-- Only one policy is effective at a time in the existing runtime.
CREATE UNIQUE INDEX uq_one_active_evaluation_policy
    ON evaluation_policies (is_active) WHERE is_active;
