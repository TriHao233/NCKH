"""Unit tests for the Brevo email helper — network calls are mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core import email_service as email_module
from core.config import settings
from core.email_service import EmailService, build_email_html


@pytest.fixture
def _brevo_env(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "xkeysib-test-key")
    monkeypatch.setattr(settings, "brevo_sender_email", "noreply@qbankctu.local")
    monkeypatch.setattr(settings, "brevo_sender_name", "QBankCTU")
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    monkeypatch.setattr(settings, "brevo_api_url", "https://api.brevo.com/v3/smtp/email")
    monkeypatch.setattr(settings, "brevo_timeout_seconds", 5.0)


def _mock_response(status_code=201, text="", json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.json.return_value = json_data or {}
    return response


def test_send_success_calls_brevo(_brevo_env):
    service = EmailService()
    with patch("core.email_service.httpx.post", return_value=_mock_response(201)) as mock_post:
        ok = service.send(
            to_email="user@example.com",
            to_name="Nguyễn Văn A",
            subject="Test",
            html_body="<p>hi</p>",
        )
    assert ok is True
    mock_post.assert_called_once()
    kwargs = mock_post.call_args.kwargs
    assert kwargs["headers"]["api-key"] == "xkeysib-test-key"
    body = kwargs["json"]
    assert body["sender"] == {"email": "noreply@qbankctu.local", "name": "QBankCTU"}
    assert body["to"] == [{"email": "user@example.com", "name": "Nguyễn Văn A"}]
    assert body["subject"] == "Test"
    assert body["htmlContent"] == "<p>hi</p>"


def test_send_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "brevo_api_key", "")
    monkeypatch.setattr(settings, "brevo_sender_email", "")
    monkeypatch.setattr(settings, "email_notifications_enabled", True)
    service = EmailService()
    with patch("core.email_service.httpx.post") as mock_post:
        assert service.send(to_email="a@b.c", subject="s", html_body="") is False
    mock_post.assert_not_called()


def test_send_returns_false_when_disabled(_brevo_env, monkeypatch):
    monkeypatch.setattr(settings, "email_notifications_enabled", False)
    service = EmailService()
    with patch("core.email_service.httpx.post") as mock_post:
        assert service.send(to_email="a@b.c", subject="s", html_body="") is False
    mock_post.assert_not_called()


def test_send_returns_false_when_no_recipient(_brevo_env):
    service = EmailService()
    with patch("core.email_service.httpx.post") as mock_post:
        assert service.send(to_email=None, subject="s", html_body="") is False
        assert service.send(to_email="", subject="s", html_body="") is False
    mock_post.assert_not_called()


def test_send_swallows_brevo_error(_brevo_env):
    service = EmailService()
    with patch(
        "core.email_service.httpx.post",
        return_value=_mock_response(status_code=400, text="Bad request"),
    ) as mock_post:
        ok = service.send(to_email="a@b.c", subject="s", html_body="")
    assert ok is False
    mock_post.assert_called_once()


def test_send_swallows_network_exception(_brevo_env):
    service = EmailService()
    with patch("core.email_service.httpx.post", side_effect=RuntimeError("boom")):
        assert service.send(to_email="a@b.c", subject="s", html_body="") is False


def test_build_email_html_escapes_content():
    body = build_email_html(
        title="Xin chào & <script>",
        paragraphs=["Nội dung <b>an toàn</b>"],
        meta={"Mã": "CT-2026-0001", "Trống": ""},
    )
    assert "QBankCTU" in body
    assert "&lt;script&gt;" in body
    assert "&lt;b&gt;an toàn&lt;/b&gt;" in body
    assert "CT-2026-0001" in body
    # Empty meta values are omitted.
    assert "Trống" not in body


def test_build_email_html_brand_and_highlight():
    body = build_email_html(
        title="Yêu cầu liên hệ mới",
        paragraphs=["Xem chi tiết trong hệ thống."],
        highlight="Dòng đầu <script>\nDòng sau & thêm",
        highlight_label="NỘI DUNG YÊU CẦU",
    )
    assert "Hệ thống ngân hàng câu hỏi - Trường Công Nghệ Thông Tin &amp; Truyền Thông, Đại học Cần Thơ" in body
    assert "NỘI DUNG YÊU CẦU" in body
    assert "Dòng đầu &lt;script&gt;<br>Dòng sau &amp; thêm" in body
    assert "linear-gradient" not in body
