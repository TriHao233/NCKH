"""Brevo (Sendinblue) transactional email helper.

Configuration comes from env: BREVO_API_KEY, BREVO_SENDER_EMAIL,
BREVO_SENDER_NAME, EMAIL_NOTIFICATIONS_ENABLED. When config is missing or the
API call fails, this module only logs and returns False so the caller's
business flow never breaks because of email delivery.
"""

from __future__ import annotations

import html
import logging
from typing import Iterable

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


BRAND_NAME = "QBankCTU"
BRAND_TAGLINE = (
    "Hệ thống ngân hàng câu hỏi - Trường Công Nghệ Thông Tin & "
    "Truyền Thông, Đại học Cần Thơ"
)


def _html_shell(title: str, body_html: str) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{safe_title}</title></head>
<body style="margin:0;padding:0;background:#f3f6fa;color:#172b45;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;background:#f3f6fa;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="width:100%;max-width:600px;background:#ffffff;border:1px solid #dde6ef;border-top:4px solid #0c78d4;border-radius:10px;">
        <tr>
          <td style="padding:24px 28px 20px;background:#ffffff;border-bottom:1px solid #e8eef5;">
            <div style="font-size:22px;font-weight:700;line-height:1.25;color:#12395e;">{BRAND_NAME}</div>
            <div style="font-size:12px;line-height:1.55;color:#52677e;margin-top:6px;">{html.escape(BRAND_TAGLINE)}</div>
          </td>
        </tr>
        <tr><td style="padding:26px 28px 8px;">
          <h1 style="margin:0;font-size:20px;line-height:1.35;color:#12395e;overflow-wrap:break-word;">{safe_title}</h1>
        </td></tr>
        <tr><td style="padding:10px 28px 28px;font-size:14px;line-height:1.65;color:#172b45;">
          {body_html}
        </td></tr>
        <tr><td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e8eef5;font-size:12px;line-height:1.5;color:#52677e;">
          Đây là thông báo tự động từ {BRAND_NAME}. Để trao đổi, vui lòng mở yêu cầu trong hệ thống thay vì trả lời email này.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def build_email_html(
    title: str,
    paragraphs: Iterable[str],
    meta: dict | None = None,
    *,
    highlight: str | None = None,
    highlight_label: str = "Nội dung",
) -> str:
    parts: list[str] = []
    for para in paragraphs:
        parts.append(f"<p style=\"margin:0 0 16px;\">{html.escape(para)}</p>")
    if highlight:
        safe_highlight = html.escape(highlight).replace("\n", "<br>")
        parts.append(
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="width:100%;margin:18px 0 22px;border-left:3px solid #0c78d4;'
            'background:#f4f8fc;"><tr><td style="padding:16px 18px;">'
            f'<div style="font-size:11px;font-weight:700;letter-spacing:0.04em;'
            f'color:#52677e;margin-bottom:7px;">{html.escape(highlight_label)}</div>'
            f'<div style="font-size:14px;line-height:1.6;color:#172b45;'
            f'overflow-wrap:break-word;">{safe_highlight}</div>'
            '</td></tr></table>'
        )
    if meta:
        rows = "".join(
            f"<tr><td valign=\"top\" style=\"padding:9px 12px;color:#52677e;font-size:12px;"
            f"width:34%;border-bottom:1px solid #e8eef5;\">{html.escape(str(k))}</td>"
            f"<td valign=\"top\" style=\"padding:9px 12px;font-size:13px;font-weight:600;"
            f"color:#172b45;overflow-wrap:anywhere;border-bottom:1px solid #e8eef5;\">"
            f"{html.escape(str(v))}</td></tr>"
            for k, v in meta.items() if v not in (None, "")
        )
        if rows:
            parts.append(
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                'style="width:100%;margin:18px 0;border:1px solid #e8eef5;'
                'border-collapse:collapse;">' + rows + '</table>'
            )
    return _html_shell(title, "".join(parts))


class EmailService:
    """Thin wrapper around Brevo /v3/smtp/email."""

    def __init__(self) -> None:
        self.api_key = settings.brevo_api_key
        self.sender_email = settings.brevo_sender_email
        self.sender_name = settings.brevo_sender_name or BRAND_NAME
        self.enabled = bool(settings.email_notifications_enabled)
        self.api_url = settings.brevo_api_url
        self.timeout = settings.brevo_timeout_seconds

    def _configured(self) -> bool:
        if not self.enabled:
            return False
        if not self.api_key or not self.sender_email:
            logger.info("Email disabled: BREVO_API_KEY hoặc BREVO_SENDER_EMAIL chưa được cấu hình")
            return False
        return True

    def send(
        self,
        *,
        to_email: str | None,
        subject: str,
        html_body: str,
        to_name: str | None = None,
        text_body: str | None = None,
    ) -> bool:
        """Send one transactional email. Returns True on success, False otherwise.

        Never raises to the caller — email delivery must not break business flows.
        """
        if not to_email:
            logger.info("Email skipped: no recipient")
            return False
        if not self._configured():
            return False
        payload = {
            "sender": {"email": self.sender_email, "name": self.sender_name},
            "to": [{"email": to_email, "name": to_name} if to_name else {"email": to_email}],
            "subject": subject,
            "htmlContent": html_body,
        }
        if text_body:
            payload["textContent"] = text_body
        try:
            response = httpx.post(
                self.api_url,
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "api-key": self.api_key,
                },
                json=payload,
                timeout=self.timeout,
            )
            if 200 <= response.status_code < 300:
                return True
            logger.warning(
                "Brevo trả về lỗi %s khi gửi cho %s: %s",
                response.status_code, to_email, response.text[:400],
            )
        except Exception as exc:  # pragma: no cover - network errors
            logger.warning("Gửi email qua Brevo thất bại (%s): %s", to_email, exc)
        return False


def get_email_service() -> EmailService:
    return EmailService()
