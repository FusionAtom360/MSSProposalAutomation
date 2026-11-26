"""Application entry point and startup error handling."""

import logging
from collections.abc import Callable
from pathlib import Path


def main():
    """Initialize services and run the update and main application windows."""
    logger = logging.getLogger("mss_proposal_automation")
    app = None
    show_crash_alert: Callable[..., None] | None = None
    try:
        from app_logging import (
            configure_logging,
            install_exception_hooks,
            set_crash_alert_parent,
            show_crash_alert as crash_alert,
        )

        show_crash_alert = crash_alert
        logger = configure_logging()
        install_exception_hooks(logger)

        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().with_name(".env"))

        from update import UpdateManager
        from ui import App

        update = UpdateManager()
        update.run_ui()

        app = App()
        set_crash_alert_parent(app)
        app.mainloop()
    except Exception as exc:
        if show_crash_alert is None:
            logger.exception("Application startup failed")
        else:
            show_crash_alert(
                logger,
                type(exc),
                exc,
                exc.__traceback__,
                parent=app,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
