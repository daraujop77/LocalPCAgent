"""Small structured logging setup shared by M0 services."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_STANDARD_LOG_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record for easy future ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = {
            key: value for key, value in record.__dict__.items() if key not in _STANDARD_LOG_FIELDS
        }
        if context:
            payload["context"] = context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure the process root logger once, without requiring a logging package."""

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root_logger.addHandler(handler)
