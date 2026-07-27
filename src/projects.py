import json
import os
from pathlib import Path
import shutil

class ProjectManager():
    def __init__(self):
        self.projects_dir = Path("projects")
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def create_project_from_json(self, json_data):
        project_id = json_data.get("id")
        project_folder = Path(self.projects_dir) / str(project_id)
        project_folder.mkdir(parents=True, exist_ok=True)
        data_file = project_folder / "data.json"
        data_file.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
        images_folder = project_folder / "images"
        images_folder.mkdir(parents=True, exist_ok=True)
        documents_folder = project_folder / "documents"
        documents_folder.mkdir(parents=True, exist_ok=True)
        return project_id
    
    def update_project_data(self, project_id, json_data):
        project_folder = Path(self.projects_dir) / str(project_id)
        if not project_folder.exists():
            raise FileNotFoundError(f"Project folder for project {project_id} does not exist.")
        data_file = project_folder / "data.json"
        data_file.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")
    
    def open_images_folder(self, project_id):
        images_folder = Path(self.projects_dir) / str(project_id) / "images"
        if images_folder.exists():
            os.startfile(images_folder)
        else:
            raise FileNotFoundError(f"Images folder for project {project_id} does not exist.")
