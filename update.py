class Updater:
    def __init__(self, current_version, latest_version):
        self.current_version = current_version
        self.latest_version = latest_version

    def check_for_update(self):
        if self.current_version < self.latest_version:
            return True
        return False

    def perform_update(self):
        if self.check_for_update():
            