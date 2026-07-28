from dataclasses import dataclass
import os
from pathlib import Path

class SettingsManager():
    def __init__(self):
        self.auth = self.Auth()
        self.files = self.Files()
        self.load_settings()
        
    def load_settings(self):
        self.auth.email = str(os.getenv("SOLARGRAF_EMAIL", ""))
        self.auth.password = str(os.getenv("SOLARGRAF_PASSWORD", ""))
        self.repo_owner = "FusionAtom360"
        self.repo_name = "MSSProposalAutomation"
        self.repo_branch = "main"
        
        
    @dataclass
    class Auth():
        email: str = ""
        password: str = ""
    
    @dataclass
    class Files():
        projects_folder: Path = Path("./projects").resolve()
        templates_folder: Path = Path("./src/templates").resolve()
        bids_folder: Path = Path(os.getenv("BIDS_FOLDER", "./bids"))
    
    