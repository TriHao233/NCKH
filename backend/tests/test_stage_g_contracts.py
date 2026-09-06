from bson import ObjectId
import httpx
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from modules.admin.moodle_schemas import MoodleSyncPageRequest
from modules.moodle.adapter import MoodleQuestionBankAdapter, MoodleRemoteUncertain
from modules.moodle.identity_service import MoodleIdentitySyncService
from modules.moodle.publication_worker import MoodlePublicationWorker
from modules.moodle.serializer import (
    QTYPE_CAPABILITIES,
    serialize_question,
    to_moodle_xml,
    validate_target_capabilities,
)


def _serialized(qtype, options, answer):
    question_id, version_id = ObjectId(), ObjectId()
    return serialize_question(
        {"_id": question_id, "question_code": f"Q-{question_id}"},
        {
            "_id": version_id,
            "version": 3,
            "content": "Nội dung <an toàn>",
            "content_hash": "content-hash",
            "classification": {"assessment_type": qtype},
            "question_data": {"options": options, "correct_answer": answer},
        },
    )


@pytest.mark.parametrize(
    ("qtype", "options", "answer", "moodle_qtype"),
    [
        ("trac_nghiem", {"A": "a", "B": "b"}, "A", "multichoice"),
        ("tinh_huong", {"A": "a", "B": "b"}, "B", "multichoice"),
        ("nhieu_lua_chon", {"A": "a", "B": "b", "C": "c", "D": "d"}, "A,C", "multichoice"),
        ("dung_sai", {"A": "Đúng", "B": "Sai"}, "A", "truefalse"),
        ("dien_khuyet", {}, "FIFO", "shortanswer"),
        (
            "ghep_cot",
            {"1": "một", "2": "hai", "3": "ba", "A": "a", "B": "b", "C": "c", "D": "x"},
            "1-A,2-B,3-C",
            "matching",
        ),
        ("sap_xep", {"A": "một", "B": "hai", "C": "ba", "D": "bốn"}, "A,B,C,D", "ordering"),
    ],
)
def test_official_serializer_covers_typed_question_contract(qtype, options, answer, moodle_qtype):
    payload = _serialized(qtype, options, answer)
    xml = to_moodle_xml(payload)
    assert payload["moodle_qtype"] == moodle_qtype
    assert payload["payload_sha256"]
    assert f'question type="{moodle_qtype}"' in xml
    assert "&lt;an toàn&gt;" in xml


def test_ordering_requires_declared_target_capability():
    payload = _serialized("sap_xep", {"A": "1", "B": "2", "C": "3", "D": "4"}, "A,B,C,D")
    with pytest.raises(ValueError, match="qtype_ordering"):
        validate_target_capabilities(payload, {})
    validate_target_capabilities(
        payload, {"local_nckh_questionbank": True, "qtype_ordering": True}
    )
    assert "qtype_ordering" in QTYPE_CAPABILITIES["sap_xep"]["requires"]


class _Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _Client:
    def __init__(self):
        self.calls = []

    def post(self, _url, data, timeout):
        self.calls.append((data, timeout))
        if data["wsfunction"] == "local_nckh_upsert_question":
            return _Response({"questionid": 42})
        return _Response({"questionid": 42, "versionid": data.get("versionid", "v3"), "contenthash": "content-hash"})


def test_adapter_requires_runtime_secret(monkeypatch):
    monkeypatch.delenv("TEST_MOODLE_TOKEN", raising=False)
    adapter = MoodleQuestionBankAdapter(
        {
            "base_url": "https://moodle.invalid",
            "token_env_var": "TEST_MOODLE_TOKEN",
            "capabilities": {"local_nckh_questionbank": True},
        },
        client=_Client(),
    )
    with pytest.raises(ValueError, match="token runtime"):
        adapter.publish(
            _serialized("trac_nghiem", {"A": "a", "B": "b"}, "A"), course_id="1", category_id="2", idempotency_key="key"
        )


class _TimeoutClient:
    @staticmethod
    def post(*_args, **_kwargs):
        raise httpx.ReadTimeout("confirmation lost")


def test_adapter_marks_network_confirmation_loss_as_unknown(monkeypatch):
    monkeypatch.setenv("TEST_MOODLE_TOKEN", "secret")
    adapter = MoodleQuestionBankAdapter(
        {
            "base_url": "https://moodle.invalid",
            "token_env_var": "TEST_MOODLE_TOKEN",
            "capabilities": {"local_nckh_questionbank": True},
        },
        client=_TimeoutClient(),
    )
    with pytest.raises(MoodleRemoteUncertain):
        adapter.publish(
            _serialized("trac_nghiem", {"A": "a", "B": "b"}, "A"), course_id="1", category_id="2", idempotency_key="key"
        )


class _MalformedResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        raise ValueError("not json")


class _MalformedClient:
    def __init__(self, status_code):
        self.status_code = status_code

    def post(self, *_args, **_kwargs):
        return _MalformedResponse(self.status_code)


@pytest.mark.parametrize("status_code", [200, 502])
def test_adapter_treats_malformed_or_5xx_confirmation_as_uncertain(monkeypatch, status_code):
    monkeypatch.setenv("TEST_MOODLE_TOKEN", "secret")
    adapter = MoodleQuestionBankAdapter(
        {
            "base_url": "https://moodle.invalid",
            "token_env_var": "TEST_MOODLE_TOKEN",
            "capabilities": {"local_nckh_questionbank": True},
        },
        client=_MalformedClient(status_code),
    )
    with pytest.raises(MoodleRemoteUncertain):
        adapter._call("local_nckh_upsert_question", {})


def test_publication_worker_does_not_send_stale_unapproved_version():
    database = MagicMock()
    question_id, old_version_id, current_version_id = ObjectId(), ObjectId(), ObjectId()
    publication = {
        "_id": ObjectId(),
        "question_id": question_id,
        "question_version_id": old_version_id,
        "target": {"target_id": ObjectId(), "course_id": "1", "category_id": "2"},
        "idempotency_key": "key",
    }
    database.moodle_targets.find_one.return_value = {"mode": "REST_API", "is_active": True}
    database.questions.find_one.return_value = {
        "_id": question_id,
        "lifecycle_status": "ACTIVE",
        "review_status": "DRAFT",
        "current_version_id": current_version_id,
        "approved_version_id": None,
    }
    database.question_versions.find_one.return_value = {
        "_id": old_version_id,
        "question_id": question_id,
    }
    database.moodle_publications.find_one.return_value = {**publication, "status": "FAILED"}
    adapter = MagicMock()

    result = MoodlePublicationWorker(database, adapter_factory=lambda _target: adapter)._process(publication)

    adapter.publish.assert_not_called()
    assert result["status"] == "FAILED"
    updates = database.moodle_publications.update_one.call_args.args[1]["$set"]
    assert updates["status"] == "FAILED"


def test_identity_sync_rejects_missing_first_page():
    database = MagicMock()
    database.moodle_sync_pages.find_one.return_value = None
    database.moodle_sync_runs.find_one.return_value = None
    payload = MoodleSyncPageRequest(
        site_key="ctu",
        sync_id="sync-1",
        page_number=99,
        checkpoint="page-99",
        is_last_page=True,
    )

    with pytest.raises(ValueError, match="trang 1"):
        MoodleIdentitySyncService(database).sync_page(payload)
    database.subject_memberships.update_many.assert_not_called()


def test_inactive_external_identity_cannot_create_active_membership():
    database = MagicMock()
    internal_user_id = ObjectId()
    database.moodle_sync_pages.find_one.return_value = None
    database.moodle_sync_runs.find_one.return_value = None
    database.external_identities.find_one.return_value = {"internal_user_id": internal_user_id}
    database.external_identities.find_one_and_update.return_value = {
        "internal_user_id": internal_user_id,
        "is_active": False,
    }
    payload = MoodleSyncPageRequest(
        site_key="ctu",
        sync_id="sync-1",
        page_number=1,
        checkpoint="page-1",
        next_checkpoint="page-2",
        identities=[{"external_user_id": "moodle-user", "is_active": False}],
        memberships=[
            {
                "external_user_id": "moodle-user",
                "external_course_id": "course-1",
                "subject_id": str(ObjectId()),
                "external_role": "student",
                "is_active": True,
            }
        ],
    )

    MoodleIdentitySyncService(database).sync_page(payload)

    membership_update = database.subject_memberships.find_one_and_update.call_args.args[1]["$set"]
    assert membership_update["status"] == "REVOKED"


def test_versioned_moodle_plugin_declares_all_adapter_functions():
    plugin_root = Path(__file__).resolve().parents[2] / "moodle" / "local" / "nckh"
    services = (plugin_root / "db" / "services.php").read_text(encoding="utf-8")
    for function_name in (
        "local_nckh_upsert_question",
        "local_nckh_get_question",
        "local_nckh_find_question",
    ):
        assert function_name in services
    assert (plugin_root / "db" / "install.xml").is_file()
