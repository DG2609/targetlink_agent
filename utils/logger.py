"""
Cấu hình logging cho toàn bộ hệ thống.
"""

import logging
import sys
from pathlib import Path


def setup_logger(log_level: str = "INFO", log_file: str | None = None) -> None:
    """Thiết lập logging: console + optionally file.

    Args:
        log_level: "DEBUG" | "INFO" | "WARNING" | "ERROR"
        log_file: Path tới file log (None = chỉ log ra console)
    """
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%H:%M:%S"

    # Use sys.stdout directly — main.py already wraps it with UTF-8 TextIOWrapper.
    # Creating a second wrapper on the same buffer causes interleaved output.
    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout)
    ]

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
        force=True,
    )

    # Giảm noise từ thư viện ngoài
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
