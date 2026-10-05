from dotenv import load_dotenv
import logging

def main():
    load_dotenv()

    from app_logging import configure_logging, install_exception_hooks

    logger = configure_logging()
    install_exception_hooks(logger)

    try:
        from update import UpdateManager
        from ui import App

        update = UpdateManager()
        update.run_ui()

        app = App()
        app.mainloop()
    except Exception:
        logging.getLogger("mss_proposal_automation").exception("Application startup failed")
        raise


if __name__ == "__main__":
    main()
