#!/usr/bin/env python3
import logging
import sys
import os
import atexit

LOG_FILE = os.path.join(os.path.expanduser("~"), ".local", "share", "lufus", "lufus.log")

_YELLOW = "\033[33m"
_RED    = "\033[31m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"
_FMT     = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

_setup_done = False


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        if record.levelno == logging.WARNING:
            return f"{_YELLOW}{msg}{_RESET}"
        if record.levelno >= logging.ERROR:
            return f"{_RED}{_BOLD}{msg}{_RESET}"
        return msg


def setup_logging() -> None:
    global _setup_done
    if _setup_done:
        return
    _setup_done = True

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    root = logging.getLogger("lufus")
    root.setLevel(logging.DEBUG)

    plain = logging.Formatter(_FMT, _DATEFMT)
    color = _ColorFormatter(_FMT, _DATEFMT)

    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8", delay=False)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(plain)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(color)

    root.addHandler(fh)
    root.addHandler(ch)

    def _crash_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        root.critical(
            "Unhandled exception — process is about to crash",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        fh.flush()

    sys.excepthook = _crash_hook
    atexit.register(fh.flush)
    root.debug("Logging initialised — log file: %s", LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    if not name.startswith("lufus"):
        name = f"lufus.{name}"
    return logging.getLogger(name)