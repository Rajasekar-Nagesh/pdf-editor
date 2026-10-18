"""Periodic maintenance: delete expired guest files and send signature reminders.

Run as its own container: `python -m app.scheduler`. Each task is also callable from tests.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal, init_db
from .models import Job, StoredFile
from .storage import get_storage

log = logging.getLogger("pdfdesk.scheduler")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def cleanup_expired_files() -> int:
    """Delete guest files whose 1-hour lifetime has passed, plus old guest jobs."""
    now = datetime.now(timezone.utc)
    removed = 0
    with SessionLocal() as db:
        rows = db.scalars(select(StoredFile).where(StoredFile.expires_at.is_not(None), StoredFile.expires_at < now)).all()
        for row in rows:
            try:
                get_storage().delete(row.storage_key)
            except Exception as exc:
                log.warning("Could not delete object for file %s: %s", row.id, exc.__class__.__name__)
            db.delete(row)
            removed += 1
        old_jobs = db.scalars(
            select(Job).where(Job.owner_id.is_(None), Job.created_at < now - timedelta(hours=2))
        ).all()
        for job in old_jobs:
            db.delete(job)
        db.commit()
    return removed


def send_due_reminders() -> int:
    from .routers.signrequests import send_reminders_for

    days = get_settings().signature_reminder_days
    if days <= 0:
        return 0
    with SessionLocal() as db:
        return send_reminders_for(db, older_than=timedelta(days=days))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    last_reminder = 0.0
    while True:
        try:
            n = cleanup_expired_files()
            if n:
                log.info("Deleted %d expired guest file(s)", n)
            if time.time() - last_reminder > 3600:
                sent = send_due_reminders()
                last_reminder = time.time()
                if sent:
                    log.info("Sent %d signature reminder(s)", sent)
        except Exception as exc:
            log.error("Scheduler iteration failed: %s", exc.__class__.__name__)
        time.sleep(60)


if __name__ == "__main__":
    main()
