from __future__ import annotations

import hashlib
import json
import re
from html import escape


QTYPE_CAPABILITIES = {
    "trac_nghiem": {"moodle_qtype": "multichoice", "requires": ["local_nckh_questionbank"]},
    "tinh_huong": {"moodle_qtype": "multichoice", "requires": ["local_nckh_questionbank"]},
    "nhieu_lua_chon": {"moodle_qtype": "multichoice", "requires": ["local_nckh_questionbank"]},
    "dung_sai": {"moodle_qtype": "truefalse", "requires": ["local_nckh_questionbank"]},
    "dien_khuyet": {"moodle_qtype": "shortanswer", "requires": ["local_nckh_questionbank"]},
    "ghep_cot": {"moodle_qtype": "matching", "requires": ["local_nckh_questionbank"]},
    "sap_xep": {"moodle_qtype": "ordering", "requires": ["local_nckh_questionbank", "qtype_ordering"]},
}


def _qtype(version: dict) -> str:
    return str((version.get("classification") or {}).get("assessment_type") or "").lower()


def required_capabilities(version: dict) -> list[str]:
    contract = QTYPE_CAPABILITIES.get(_qtype(version))
    if not contract:
        raise ValueError(f"Dạng câu hỏi Moodle chưa được hỗ trợ: {_qtype(version)}")
    return list(contract["requires"])


def validate_target_capabilities(version: dict, capabilities: dict) -> None:
    required = (
        list(version.get("required_capabilities") or [])
        if "required_capabilities" in version
        else required_capabilities(version)
    )
    missing = [name for name in required if not capabilities.get(name)]
    if missing:
        raise ValueError("Moodle target thiếu capability: " + ", ".join(missing))


def serialize_question(question: dict, version: dict) -> dict:
    qtype = _qtype(version)
    contract = QTYPE_CAPABILITIES.get(qtype)
    if not contract:
        raise ValueError(f"Dạng câu hỏi Moodle chưa được hỗ trợ: {qtype}")
    data = version.get("question_data") or {}
    payload = {
        "schema_version": 1,
        "external_key": f"{question['_id']}:{version['_id']}",
        "question_id": str(question["_id"]),
        "version_id": str(version["_id"]),
        "version": int(version["version"]),
        "content_hash": version["content_hash"],
        "question_code": question["question_code"],
        "source_type": qtype,
        "moodle_qtype": contract["moodle_qtype"],
        "name": question["question_code"],
        "questiontext": version.get("content") or "",
        "options": data.get("options") or {},
        "correct_answer": data.get("correct_answer") or "",
        "feedback": data.get("explanation") or "",
        "required_capabilities": list(contract["requires"]),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    return payload


def _answer(text, fraction, feedback="") -> str:
    return (
        f'<answer fraction="{fraction}"><text>{escape(str(text))}</text>'
        f"<feedback><text>{escape(str(feedback))}</text></feedback></answer>"
    )


def to_moodle_xml(payload: dict) -> str:
    qtype = payload["moodle_qtype"]
    options = payload["options"]
    correct = [item.strip().upper() for item in re.split(r"[,;|]", str(payload["correct_answer"])) if item.strip()]
    common = (
        f"<name><text>{escape(payload['name'])}</text></name>"
        f'<questiontext format="html"><text>{escape(payload["questiontext"])}</text></questiontext>'
        f"<idnumber>{escape(payload['external_key'])}</idnumber>"
    )
    if qtype == "truefalse":
        yes = correct[0] in {"A", "TRUE", "T", "ĐÚNG", "DUNG"}
        body = _answer("true", 100 if yes else 0) + _answer("false", 0 if yes else 100)
    elif qtype == "shortanswer":
        body = "<usecase>0</usecase>" + "".join(_answer(value, 100, payload["feedback"]) for value in correct)
    elif qtype == "matching":
        pairs = re.findall(r"(\d+)\s*-\s*([A-Za-z])", payload["correct_answer"])
        body = "".join(
            f'<subquestion format="html"><text>{escape(str(options[left]))}</text>'
            f"<answer><text>{escape(str(options[right.upper()]))}</text></answer></subquestion>"
            for left, right in pairs
        )
    elif qtype == "ordering":
        rank = {key: index + 1 for index, key in enumerate(correct)}
        body = "".join(
            f'<answer fraction="0"><text>{escape(str(value))}</text><correctorder>{rank[key]}</correctorder></answer>'
            for key, value in options.items()
        )
    else:
        multiple = payload["source_type"] == "nhieu_lua_chon"
        fraction = round(100 / len(correct), 6) if multiple and correct else 100
        body = f"<single>{str(not multiple).lower()}</single><shuffleanswers>true</shuffleanswers>" + "".join(
            _answer(value, fraction if key.upper() in correct else 0, payload["feedback"])
            for key, value in options.items()
        )
    return f'<?xml version="1.0" encoding="UTF-8"?><quiz><question type="{qtype}">{common}{body}</question></quiz>'
