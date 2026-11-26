import logging
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app_logging


def test_main_reports_startup_error_if_logging_setup_fails(monkeypatch):
    import main

    errors = []

    def fail_logging_setup():
        raise RuntimeError("logging setup failed")

    monkeypatch.setattr(app_logging, "configure_logging", fail_logging_setup)
    monkeypatch.setattr(
        app_logging,
        "show_crash_alert",
        lambda logger, exc_type, exc_value, exc_traceback, **kwargs: errors.append(
            exc_value
        ),
    )

    assert main.main() == 1
    assert len(errors) == 1
    assert str(errors[0]) == "logging setup failed"


def test_log_contains_only_current_run_and_appends_after_reconfiguration(
    tmp_path, monkeypatch
):
    logger = logging.getLogger(app_logging.LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    monkeypatch.setattr(app_logging, "_logging_started", False)
    log_path = tmp_path / "app.log"
    log_path.write_text("previous run\n", encoding="utf-8")

    app_logging.configure_logging(log_dir=tmp_path)
    logger.info("current run before update")

    for handler in list(logger.handlers):
        handler.flush()
        handler.close()
        logger.removeHandler(handler)
    app_logging.configure_logging(log_dir=tmp_path)
    logger.info("current run after update")

    for handler in logger.handlers:
        handler.flush()
    log_text = log_path.read_text(encoding="utf-8")

    assert "previous run" not in log_text
    assert "current run before update" in log_text
    assert "current run after update" in log_text

    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_support_email_url_contains_complete_log_in_body():
    log_text = "Traceback (most recent call last):\n" + ("failure details\n" * 100)

    url = app_logging.build_support_email_url(log_text)

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "mailto"
    assert parsed.path == "joe.yakligian@gmail.com"
    assert query["body"] == [log_text]
