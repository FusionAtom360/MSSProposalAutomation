import json
import urllib.request
from pathlib import Path
import shutil
import tempfile

class UpdateManager:
    REPO = "FusionAtom360/MSSProposalAutomation"
    RAW = "https://raw.githubusercontent.com/FusionAtom360/MSSProposalAutomation/main"
    VENV = ".venv"

    EXCLUDE = {
        ".env",
        ".gitignore"
    }

    def __init__(self):
        self.root = Path(__file__).parent.parent
        self.src = self.root / "src"
        with open(self.src / "details.json", encoding="utf-8") as f:
            self.details = json.load(f)
        self.current = self.details["version"]

    def latest_version(self):
        url = f"{self.RAW}/src/details.json"
        with urllib.request.urlopen(url) as r:
            return json.load(r)["version"]

    def update_available(self):
        return self.current != self.latest_version()

    def download_tree(self):
        url = f"https://api.github.com/repos/" f"{self.REPO}/git/trees/main?recursive=1"
        with urllib.request.urlopen(url) as r:
            tree = json.load(r)["tree"]
        files = []

        for item in tree:
            path = item["path"]
            if not path.startswith("src/"):
                continue
            rel = Path(path[4:])
            if rel.name in self.EXCLUDE:
                continue
            files.append(rel)
        return files

    def update(self):
        files = self.download_tree()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for file in files:
                url = f"{self.RAW}/src/{file}"
                data = urllib.request.urlopen(url).read()
                target = tmp / file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

            for file in files:
                src = tmp / file
                dst = self.src / file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
