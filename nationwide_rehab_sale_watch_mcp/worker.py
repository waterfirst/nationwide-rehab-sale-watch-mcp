from __future__ import annotations

import json
import logging
import os
import signal
import threading
from typing import Any

from .server import run_persistent_scan


logger = logging.getLogger("rehab-watch-scanner")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
stop_event = threading.Event()


def _positive_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(value, maximum))


def scan_once(max_pages: int) -> dict[str, Any]:
    result = run_persistent_scan(max_pages=max_pages, enrich_details=False)
    summary = {
        key: result[key]
        for key in ("run_id", "status", "rows_seen", "new_count", "candidate_count", "errors", "observed_at")
    }
    logger.info("scan_complete %s", json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    interval_minutes = _positive_int("REHAB_WATCH_SCAN_INTERVAL_MINUTES", 360, 15, 24 * 60)
    max_pages = _positive_int("REHAB_WATCH_SCAN_MAX_PAGES", 2, 1, 10)

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    logger.info("scanner_started interval_minutes=%s max_pages=%s", interval_minutes, max_pages)

    while not stop_event.is_set():
        try:
            scan_once(max_pages)
        except Exception:
            logger.exception("scan_failed")
        stop_event.wait(interval_minutes * 60)

    logger.info("scanner_stopped")


if __name__ == "__main__":
    main()
