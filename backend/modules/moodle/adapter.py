from __future__ import annotations

import os

import httpx

from modules.moodle.serializer import validate_target_capabilities


class MoodleRemoteUncertain(RuntimeError):
    """The write may have reached Moodle, so blind retry is unsafe."""


class MoodleQuestionBankAdapter:
    UPSERT_FUNCTION = "local_nckh_upsert_question"
    VERIFY_FUNCTION = "local_nckh_get_question"
    FIND_FUNCTION = "local_nckh_find_question"

    def __init__(self, target: dict, *, client=httpx):
        self.target = target
        self.client = client

    def _token(self) -> str:
        token = os.getenv(self.target.get("token_env_var") or "")
        if not token:
            raise ValueError("Moodle target chưa có token runtime")
        return token

    def _call(self, function: str, data: dict) -> dict:
        try:
            response = self.client.post(
                f"{self.target['base_url'].rstrip('/')}/webservice/rest/server.php",
                data={"wstoken": self._token(), "wsfunction": function, "moodlewsrestformat": "json", **data},
                timeout=15,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise MoodleRemoteUncertain(str(exc)) from exc
        payload = response.json()
        if response.status_code >= 500:
            raise MoodleRemoteUncertain(f"Moodle HTTP {response.status_code}")
        if response.status_code >= 400 or payload.get("exception"):
            raise ValueError(payload.get("message") or f"Moodle HTTP {response.status_code}")
        return payload

    def publish(self, serialized: dict, *, course_id: str, category_id: str, idempotency_key: str) -> dict:
        validate_target_capabilities(serialized, self.target.get("capabilities") or {})
        allowed = {str(value) for value in self.target.get("allowed_course_ids") or []}
        if allowed and str(course_id) not in allowed:
            raise PermissionError("Course không thuộc allowlist của Moodle target")
        result = self._call(
            self.UPSERT_FUNCTION,
            {
                "courseid": course_id,
                "categoryid": category_id,
                "idempotencykey": idempotency_key,
                "payloadjson": __import__("json").dumps(serialized, ensure_ascii=False),
            },
        )
        remote_id = str(result.get("questionid") or "")
        if not remote_id:
            raise MoodleRemoteUncertain("Moodle không trả questionid")
        verified = self.verify(remote_id, serialized["version_id"], serialized["content_hash"])
        return {"remote_id": remote_id, "verified": verified, "raw": result}

    def verify(self, remote_id: str, version_id: str, content_hash: str) -> bool:
        result = self._call(self.VERIFY_FUNCTION, {"questionid": remote_id})
        return str(result.get("versionid")) == str(version_id) and result.get("contenthash") == content_hash

    def find_by_idempotency_key(self, idempotency_key: str) -> dict | None:
        result = self._call(self.FIND_FUNCTION, {"idempotencykey": idempotency_key})
        return result if result.get("questionid") else None
