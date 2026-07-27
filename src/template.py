from data import DataManager

class TemplateManager:
    def __init__(self, data):
        self.templates = {}
        self.update(data)
    
    def update(self, data: DataManager):
        self.templates[r"{{CLIENT_NAME}}"] = data.client.name
        self.templates[r"{{CLIENT_FIRST_NAME}}"] = data.client.first_name
        self.templates[r"{{CLIENT_LAST_NAME}}"] = data.client.last_name
        self.templates[r"{{CLIENT_PHONE}}"] = data.client.phone
        self.templates[r"{{CLIENT_EMAIL}}"] = data.client.email
        self.templates[r"{{PROJECT_NAME}}"] = data.project.name

    def resolve(self, template_name):
        return self.templates.get(template_name, template_name)
