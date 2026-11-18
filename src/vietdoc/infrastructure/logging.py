"""JSON-lines logging for Python compute processes.

Only allowlisted structured fields are emitted: IDs, stage, timing, status and
error codes. Document text, OCR output, payloads and secrets are never logged.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

ALLOWED_FIELDS = (
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "job_id",
    "run_id",
    "attempt_id",
    "manifest_id",
    "code",
    "stage",
    "releases",
    "release_errors",
    "reasons",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in ALLOWED_FIELDS:
            if field in record.__dict__:
                entry[field] = record.__dict__[field]
        if record.exc_info and record.exc_info[0] is not None:
            entry["error_type"] = record.exc_info[0].__name__
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers[:] = []
        logging.getLogger(name).propagate = True
    # The service writes its own structured access line; drop uvicorn's duplicate.
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = []
    access.propagate = False
