"""RQ worker entry point: `python -m app.worker`."""
import logging

from redis import Redis
from rq import Queue, Worker

from .config import get_settings
from .db import init_db


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    conn = Redis.from_url(get_settings().redis_url)
    Worker([Queue("pdfdesk", connection=conn)], connection=conn).work(with_scheduler=False)


if __name__ == "__main__":
    main()
