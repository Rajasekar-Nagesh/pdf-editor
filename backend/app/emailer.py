"""Outgoing email via SMTP. If SMTP is not configured, emails are skipped (logged without content)."""
import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

log = logging.getLogger("pdfdesk.email")

# In tests we capture outgoing mail here instead of sending it.
OUTBOX: list[EmailMessage] = []


def send_email(to: str, subject: str, text: str, attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    for filename, data, mime in attachments or []:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    if s.environment == "test":
        OUTBOX.append(msg)
        return True
    if not s.smtp_host:
        if s.environment == "development":
            # Local development only: print the email so links (reset, signing) can be used without SMTP.
            log.warning("SMTP not configured (development) - email to %s:\nSubject: %s\n%s", to, subject, text)
        else:
            log.warning("SMTP not configured; skipped email with subject %r", subject)
        return False
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # never crash a request because mail failed
        log.error("Failed to send email %r: %s", subject, exc.__class__.__name__)
        return False
