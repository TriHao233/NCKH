from bson import ObjectId
import httpx
import pytest

from modules.moodle.adapter import MoodleQuestionBankAdapter, MoodleRemoteUncertain
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
