"""Structured JSON logging setup."""
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path


def get_logger(name: str, log_dir: Path, run_id: str | None = None) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    base = logging.getLogger(name)
    base.setLevel(logging.DEBUG)
    if not base.handlers:
        fh = logging.FileHandler(log_dir / "pipeline.jsonl")
        fh.setFormatter(_JsonFormatter())
        base.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        base.addHandler(sh)
    if run_id:
        return _RunAdapter(base, run_id)
    return base


def log_event(logger: logging.Logger, level: str, event: str, **kwargs):
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **kwargs,
    }
    # If this is a _RunAdapter the extra run_id is injected automatically
    getattr(logger, level.lower())(json.dumps(payload))


class _RunAdapter(logging.LoggerAdapter):
    """Injects run_id into every log record message."""

    def __init__(self, logger: logging.Logger, run_id: str) -> None:
        super().__init__(logger, {})
        self._run_id = run_id

    def process(self, msg, kwargs):
        # msg is already a JSON string from log_event — decode, inject, re-encode
        try:
            payload = json.loads(msg)
            payload["run_id"] = self._run_id
            return json.dumps(payload), kwargs
        except (ValueError, TypeError):
            return msg, kwargs


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return record.getMessage()
