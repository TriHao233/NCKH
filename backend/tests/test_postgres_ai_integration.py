"""Run with RUN_POSTGRES_INTEGRATION=1 and POSTGRES_DSN against a test database."""

import os
import uuid

import pytest

from core.config import settings
from core.postgres import postgres_connection
from modules.catalog.postgres_ai_repository import PostgresAiRepository
from modules.catalog.schemas import AiModelPayload, PromptTemplatePayload, EvaluationPolicyPayload
from modules.users.postgres_repository import PostgresUserRepository


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1" or not settings.postgres_dsn,
    reason="Requires an explicitly configured PostgreSQL test database",
)


def test_versioned_ai_configuration_and_activation():
    repo = PostgresAiRepository()
    suffix = uuid.uuid4().hex[:12]
    code = f"test-{suffix}"
    prompt_key = f"test:{suffix}"
    policy_name = f"Test {suffix}"
    actor = PostgresUserRepository().create({
        "firebase_uid": f"test-admin-{suffix}",
        "email": f"test-admin-{suffix}@example.test",
        "display_name": "Test Admin", "role": "Admin",
    })
    try:
        first = repo.save_model(AiModelPayload(
            model_code=code, model_name="test:1", display_name="Test",
            runtime="OLLAMA", capabilities=["QUESTION_GENERATION"],
            config={"temperature": 0.1},
        ), actor_id=actor["_id"])
        second = repo.save_model(AiModelPayload(
            model_code=code, model_name="test:2", display_name="Test",
            runtime="OLLAMA", capabilities=["QUESTION_GENERATION"],
            config={"temperature": 0.2},
        ), actor_id=actor["_id"])
        assert first["version"] == 1
        assert second["version"] == 2
        assert repo.model(code)["model_name"] == "test:2"
        assert len(repo.model_versions(code)) == 2
        assert repo.activate_model_version(code, 1, actor_id=actor["_id"])["model_name"] == "test:1"
        assert repo.activate_model_version(code, 2, actor_id=actor["_id"])["model_name"] == "test:2"
        assert repo.activate_model(code, False, actor_id=actor["_id"])["is_active"] is False
        with pytest.raises(ValueError, match="secret"):
            repo.save_model(AiModelPayload(
                model_code=code, model_name="bad", display_name="Test",
                runtime="OLLAMA", capabilities=["QUESTION_GENERATION"],
                config={"api_key": "forbidden"},
            ))

        prompt = repo.save_prompt(PromptTemplatePayload(
            template_key=prompt_key, kind="GENERATION", name="Test",
            prompt_body="Version 1", is_active=True,
        ), actor_id=actor["_id"])
        assert prompt["version"] == 1
        assert repo.prompt(prompt_key, active_only=True)["prompt_body"] == "Version 1"
        next_prompt = repo.save_prompt(PromptTemplatePayload(
            template_key=prompt_key, kind="GENERATION", name="Test",
            prompt_body="Version 2", is_active=True,
        ))
        assert next_prompt["version"] == 2
        assert repo.activate_prompt(prompt_key, 1, True, actor_id=actor["_id"])["is_active"] is True
        assert repo.prompt(prompt_key, active_only=True)["prompt_body"] == "Version 1"
        with pytest.raises(ValueError, match="bất biến"):
            repo.save_prompt(PromptTemplatePayload(
                template_key=prompt_key, kind="GENERATION", name="Test",
                prompt_body="Mutated", create_new_version=False,
            ))

        policy = repo.save_policy(EvaluationPolicyPayload(
            policy_name=policy_name, weights={"faithfulness": 1.0},
            thresholds={"yellow_min": 0.3, "pass_min": 0.5, "green_min": 0.7},
            is_active=False,
        ))
        assert policy["version"] == 1
        assert repo.save_policy(EvaluationPolicyPayload(
            policy_name=policy_name, weights={"faithfulness": 0.8},
            thresholds={"yellow_min": 0.3, "pass_min": 0.6, "green_min": 0.8},
            is_active=False,
        ))["version"] == 2
        with postgres_connection() as conn:
            audit_count = conn.execute(
                "SELECT count(*) AS n FROM audit_logs WHERE actor_user_id=%s",
                (str(actor["_id"]),),
            ).fetchone()["n"]
        assert audit_count >= 4
    finally:
        with postgres_connection() as conn:
            with conn.transaction():
                conn.execute("DELETE FROM audit_logs WHERE actor_user_id=%s", (str(actor["_id"]),))
                conn.execute("DELETE FROM prompt_templates WHERE template_key=%s", (prompt_key,))
                conn.execute("DELETE FROM evaluation_policies WHERE policy_name=%s", (policy_name,))
                conn.execute("UPDATE ai_models SET active_version_id=NULL WHERE model_code=%s", (code,))
                conn.execute("DELETE FROM ai_model_versions WHERE model_id IN (SELECT id FROM ai_models WHERE model_code=%s)", (code,))
                conn.execute("DELETE FROM ai_models WHERE model_code=%s", (code,))
                conn.execute("DELETE FROM users WHERE id=%s", (str(actor["_id"]),))


def test_default_policy_is_added_once_and_replaces_only_an_earlier_default():
    repo = PostgresAiRepository()
    suffix = uuid.uuid4().hex[:12]
    default_name, admin_name, late_name = (
        f"Test default {suffix}", f"Test admin {suffix}", f"Test late default {suffix}"
    )
    weights = {"faithfulness": 1.0}
    current = {"yellow_min": 0.5, "pass_min": 0.7, "green_min": 0.75}
    superseded = (0.8, 0.65)

    def save(name: str, pass_min: float) -> dict:
        return repo.save_policy(EvaluationPolicyPayload(
            policy_name=name, weights=weights,
            thresholds={"yellow_min": 0.5, "pass_min": pass_min, "green_min": 0.8},
            is_active=True,
        ))

    with postgres_connection() as conn:
        active_before = [row["id"] for row in conn.execute(
            "SELECT id FROM evaluation_policies WHERE is_active"
        ).fetchall()]
    try:
        save(default_name, 0.8)
        added = repo.ensure_default_policy(default_name, weights, current, superseded)
        assert (added["version"], added["is_active"], added["thresholds"]) == (2, True, current)
        assert repo.policy(active_only=True)["_id"] == added["_id"]
        assert repo.ensure_default_policy(default_name, weights, current, superseded) is None

        # The active policy is one an admin configured: the default is added but not activated.
        save(admin_name, 0.8)
        added = repo.ensure_default_policy(late_name, weights, current, superseded)
        assert (added["version"], added["is_active"]) == (1, False)
        assert repo.policy(active_only=True)["policy_name"] == admin_name
    finally:
        with postgres_connection() as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM evaluation_policies WHERE policy_name = ANY(%s)",
                    ([default_name, admin_name, late_name],),
                )
                conn.execute(
                    "UPDATE evaluation_policies SET is_active=true WHERE id = ANY(%s)",
                    (active_before,),
                )
