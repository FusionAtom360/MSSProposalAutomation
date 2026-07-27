from dotenv import load_dotenv

from ui import App
from update import UpdateManager
load_dotenv()

def main():
    update = UpdateManager()
    if update.check_for_update():
        update.perform_update()

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
