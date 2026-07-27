from dotenv import load_dotenv

from ui import App
from update import UpdateManager
load_dotenv()

def main():
    update = UpdateManager()
    update.run_ui()

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
