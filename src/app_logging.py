"""Application logging and uncaught-exception reporting."""

from __future__ import annotations

import logging
import sys
import threading
import traceback
from pathlib import Path
from tkinter import Button, Label, TclError, Tk, Toplevel
from urllib.parse import urlencode
import webbrowser

LOGGER_NAME = "mss_proposal_automation"
_logging_started = False
_crash_alert_parent = None


def configure_logging(
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> logging.Logger:
    """Configure the application file logger once and return it."""
    global _logging_started

    logger = logging.getLogger(LOGGER_NAME)

    if logger.handlers:
        return logger

    log_dir = log_dir or Path(__file__).resolve().parent / "logs"
    print(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.FileHandler(
        log_dir / "app.log",
        mode="a" if _logging_started else "w",
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            "%Y-%m-%d %H:%M:%S",
        )
    )

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    _logging_started = True
    return logger


def set_crash_alert_parent(parent) -> None:
    """Set the Tk window that should own crash alerts."""
    global _crash_alert_parent
    _crash_alert_parent = parent


def build_support_email_url(log_text: str) -> str:
    """Build a support email URL containing the supplied log text."""
    query = urlencode(
        {
            "subject": "MSS Proposal Automation crash report",
            "body": log_text,
        }
    )
    return f"mailto:joe.yakligian@gmail.com?{query}"


def _read_latest_log(logger: logging.Logger) -> str:
    """Flush and read the first configured file log, or return an error message."""
    for handler in logger.handlers:
        handler.flush()

    for handler in logger.handlers:
        filename = getattr(handler, "baseFilename", None)
        if filename:
            try:
                return Path(filename).read_text(encoding="utf-8")
            except OSError:
                break

    return "The application log could not be read."


def show_crash_alert(
    logger: logging.Logger,
    exc_type,
    exc_value,
    exc_traceback,
    *,
    parent=None,
) -> None:
    """Log an uncaught exception and display a dialog with the latest log."""
    logger.critical(
        "Application crashed",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    log_text = _read_latest_log(logger)
    if log_text == "The application log could not be read.":
        log_text += "\n\nCrash traceback:\n"
        log_text += "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
    parent = parent or _crash_alert_parent

    if parent is not None and threading.current_thread() is not threading.main_thread():
        try:
            parent.after(
                0,
                lambda: _show_crash_dialog(log_text, parent),
            )
            return
        except TclError:
            pass

    _show_crash_dialog(log_text, parent)


def report_tk_callback_exception(
    exc_type,
    exc_value,
    exc_traceback,
    *,
    parent=None,
) -> None:
    """Forward an uncaught Tk callback exception to the crash alert handler."""
    show_crash_alert(
        logging.getLogger(LOGGER_NAME),
        exc_type,
        exc_value,
        exc_traceback,
        parent=parent,
    )


def _show_crash_dialog(log_text: str, parent=None) -> None:
    """Display a modal crash dialog with email-support and close actions."""
    dialog: Tk | Toplevel
    if parent is None:
        dialog = Tk()
    else:
        try:
            if not parent.winfo_exists():
                parent = None
        except TclError:
            parent = None
        dialog = Toplevel(parent) if parent is not None else Tk()

    dialog.title("MSS Proposal Automation")
    dialog.resizable(False, False)
    Label(
        dialog,
        text=(
            "The application encountered an unexpected error.\n"
            "You can email the latest run log to support."
        ),
        justify="left",
        padx=20,
        pady=16,
    ).pack(fill="x")
    Button(
        dialog,
        text="Email support",
        command=lambda: webbrowser.open(build_support_email_url(log_text)),
    ).pack(side="left", padx=(20, 8), pady=(0, 16))
    Button(dialog, text="Close", command=dialog.destroy).pack(
        side="left", padx=(8, 20), pady=(0, 16)
    )
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    dialog.grab_set()
    if parent is None:
        dialog.mainloop()
    else:
        dialog.wait_window()


def install_exception_hooks(logger: logging.Logger | None = None) -> None:
    """Install process and thread exception hooks for application crashes."""
    logger = logger or logging.getLogger(LOGGER_NAME)

    def handle_exception(exc_type, exc_value, exc_traceback):
        """Report uncaught main-thread exceptions, preserving interrupts."""
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        show_crash_alert(logger, exc_type, exc_value, exc_traceback)

    def handle_thread_exception(args):
        """Log and report an uncaught worker-thread exception."""
        if issubclass(args.exc_type, KeyboardInterrupt):
            return

        logger.error(
            "Uncaught thread exception in %s",
            getattr(args.thread, "name", "unknown"),
        )
        show_crash_alert(logger, args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
