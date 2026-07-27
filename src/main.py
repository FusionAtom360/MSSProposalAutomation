from ui import App
from update import UpdateManager

def main():
    update = UpdateManager()
    if update.check_for_update():
        update.perform_update()

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
