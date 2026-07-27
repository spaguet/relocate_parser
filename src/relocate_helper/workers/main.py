"""RQ worker entrypoint."""

from __future__ import annotations

import sys

from rq.worker import Worker

from relocate_helper.common.config import get_settings
from relocate_helper.common.logging import configure_logging, get_logger
from relocate_helper.workers.queue import get_redis_connection

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)

    conn = get_redis_connection(settings)
    queues = [settings.rq_default_queue]
    logger.info("worker_starting", queues=queues)

    worker = Worker(queues, connection=conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("worker_stopped")
        sys.exit(0)
