import json

class Updater:
    def __init__(self, current_version, latest_version):
        with open('details.json', 'r') as f:
            data = json.load(f)
        self.current_version = data['version']
        
        self.latest_version = 

    def check_for_update(self):
        if self.current_version < self.latest_version:
            return True
        return False

    def perform_update(self):
        if self.check_for_update():
            
