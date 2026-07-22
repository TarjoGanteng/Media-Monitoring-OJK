"""
services/terminal_logger.py - Handler untuk menangkap log sistem dan menyajikannya ke Terminal Web Vercel
"""

import logging
import time
from collections import deque
from datetime import datetime
import threading

# Buffer penyimpanan log dalam memori (maks 300 baris terbaru)
_LOG_BUFFER = deque(maxlen=300)
_LOG_ID_COUNTER = 0
_BUFFER_LOCK = threading.Lock()


class TerminalLogHandler(logging.Handler):
    """Logging handler khusus yang menyimpan log ke memory buffer untuk terminal web UI."""

    def emit(self, record):
        global _LOG_ID_COUNTER
        try:
            msg = self.format(record)
            with _BUFFER_LOCK:
                _LOG_ID_COUNTER += 1
                entry = {
                    "id": _LOG_ID_COUNTER,
                    "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                    "level": record.levelname,
                    "name": record.name,
                    "message": msg,
                }
                _LOG_BUFFER.append(entry)
        except Exception:
            self.handleError(record)


# Flag agar handler hanya di-attach sekali
_handler_installed = False


def setup_terminal_logger():
    """Memasang TerminalLogHandler ke root logger Python."""
    global _handler_installed
    if _handler_installed:
        return

    handler = TerminalLogHandler()
    formatter = logging.Formatter("[%(levelname)s] [%(name)s] %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    # Tambahkan log selamat datang pertama kali
    log_terminal_message("SYSTEM", "INFO", "Vercel Live Terminal Logger initialized successfully.")
    log_terminal_message("AIReview", "INFO", "Monitoring 24/7 AI Engine & Guardrail system active.")

    _handler_installed = True


def log_terminal_message(module: str, level: str, message: str):
    """Fungsi helper untuk menambahkan log manual ke terminal web."""
    global _LOG_ID_COUNTER
    with _BUFFER_LOCK:
        _LOG_ID_COUNTER += 1
        entry = {
            "id": _LOG_ID_COUNTER,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "level": level.upper(),
            "name": module,
            "message": message,
        }
        _LOG_BUFFER.append(entry)


def get_terminal_logs(since_id: int = 0) -> list:
    """Mengembalikan daftar log terbaru yang ID-nya > since_id."""
    with _BUFFER_LOCK:
        if since_id <= 0:
            return list(_LOG_BUFFER)
        return [log for log in _LOG_BUFFER if log["id"] > since_id]
