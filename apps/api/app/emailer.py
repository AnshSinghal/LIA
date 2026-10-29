"""Email is sent only after an explicit confirm flag, and only with SMTP env vars."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Callable, Mapping

def is_email_request(message: str) -> bool:
    text = message.lower()
    return "e-mail" in text or "email" in text or ("data owner" in text and "send" in text)


REQUIRED_SMTP = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "DATA_OWNER_EMAIL",
)


def confirm_email(
    confirm: bool,
    env: Mapping[str, str],
    draft: str | None,
    send: Callable[[str], None],
) -> dict:
    if confirm is not True:
        return {
            "ok": False,
            "smtp_attempted": False,
            "error": "Confirmation is required before any email is sent.",
        }
    missing = [key for key in REQUIRED_SMTP if not str(env.get(key) or "").strip()]
    if missing:
        return {
            "ok": False,
            "smtp_attempted": False,
            "error": "SMTP is not configured. Missing: " + ", ".join(missing) + ".",
        }
    if not draft:
        return {
            "ok": False,
            "smtp_attempted": False,
            "error": "No draft is stored for this thread.",
        }
    send(draft)
    return {"ok": True, "smtp_attempted": True, "error": None}


def smtp_send(body: str, env: Mapping[str, str]) -> None:
    """Open a real SMTP connection. Tests must not call this against the public internet."""
    message = EmailMessage()
    message["From"] = env["SMTP_FROM"]
    message["To"] = env["DATA_OWNER_EMAIL"]
    message["Subject"] = "LIA utilisation draft"
    message.set_content(body)
    with smtplib.SMTP(env["SMTP_HOST"], int(env["SMTP_PORT"]), timeout=10) as client:
        client.starttls()
        client.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
        client.send_message(message)
