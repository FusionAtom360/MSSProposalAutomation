from utils.updater import Updater

if __name__ == "__main__":
    updater = Updater()
    if updater.check_for_update():
        updater.perform_update()
    else:
        print("Already up to date.")

print("Versioning test again!")
