from __future__ import annotations

from datetime import datetime
import logging
import os
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
DEFAULT_APP_LOG_PREFIX = "app"
REQUEST_LOG_SKIP_PATHS = {
    "/api/active/version",
    "/favicon.ico",
}


class DailyLogFileHandler(logging.Handler):
    terminator = "\n"

    def __init__(self, log_dir: Path, prefix: str, encoding: str = "utf-8") -> None:
        super().__init__()
        self.log_dir = log_dir
        self.prefix = prefix
        self.encoding = encoding
        self._current_path: Path | None = None
        self._stream = None

    def _resolve_path(self) -> Path:
        day_key = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{self.prefix}_{day_key}.log"

    def _ensure_stream(self) -> None:
        path = self._resolve_path()
        if self._current_path == path and self._stream:
            return
        if self._stream:
            self._stream.close()
        self._current_path = path
        self._stream = open(path, "a", encoding=self.encoding)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.acquire()
            self._ensure_stream()
            msg = self.format(record)
            self._stream.write(msg + self.terminator)
            self._stream.flush()
        except Exception:
            self.handleError(record)
        finally:
            self.release()

    def close(self) -> None:
        try:
            self.acquire()
            if self._stream:
                self._stream.close()
                self._stream = None
        finally:
            self.release()
        super().close()


def _resolve_log_dir() -> Path:
    raw = (os.getenv("SUPPORTHUB_LOG_DIR") or "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_LOG_DIR


def configure_daily_app_logging() -> logging.Logger:
    log_dir = _resolve_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("supporthub")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler_exists = False
    for handler in logger.handlers:
        if isinstance(handler, DailyLogFileHandler):
            handler_exists = True
            break

    if not handler_exists:
        handler = DailyLogFileHandler(log_dir, DEFAULT_APP_LOG_PREFIX, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s | %(message)s",
                "%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)

    return logger


def get_supporthub_logger(name: str) -> logging.Logger:
    configure_daily_app_logging()
    return logging.getLogger(f"supporthub.{name}")


def should_skip_request_logging(path: str) -> bool:
    return (path or "").strip() in REQUEST_LOG_SKIP_PATHS
