import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class Updater:
    REPO_BASE_URL = "https://raw.githubusercontent.com/FusionAtom360/MSSProposalAutomation/main"
    FILES_TO_UPDATE = [
        "main.py",
        "ui.py",
        "solargraf.py",
        "update.py",
        "details.json",
    ]

    def __init__(self, current_version=None, latest_version=None):
        self.base_dir = Path(__file__).resolve().parents[1]
        self.details_path = self.base_dir / "details.json"

        with self.details_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.current_version = current_version or data.get("version", "0.0.0")
        self.latest_version = latest_version or self._fetch_latest_version()

    def _fetch_latest_version(self):
        try:
            with urlopen(f"{self.REPO_BASE_URL}/details.json", timeout=10) as response:
                data = json.load(response)
            return data.get("version", self.current_version)
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            return self.current_version

    @staticmethod
    def _parse_version(version):
        match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(version))
        if not match:
            return (0, 0, 0)
        return tuple(int(part or 0) for part in match.groups())

    def check_for_update(self):
        current_version = self._parse_version(self.current_version)
        latest_version = self._parse_version(self.latest_version)
        return current_version < latest_version

    def perform_update(self):
        temp_dir = Path(tempfile.mkdtemp(prefix="mss_update_", dir=str(self.base_dir)))
        try:
            self._download_files(temp_dir)
            self._replace_files(temp_dir)
            self._launch_main_script()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _download_files(self, temp_dir):
        for relative_path in self.FILES_TO_UPDATE:
            remote_url = f"{self.REPO_BASE_URL}/{relative_path}"
            destination = temp_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urlopen(remote_url, timeout=15) as response:
                    destination.write_bytes(response.read())
            except (URLError, HTTPError, TimeoutError):
                raise RuntimeError(f"Failed to download {remote_url}")

    def _replace_files(self, temp_dir):
        for relative_path in self.FILES_TO_UPDATE:
            source = temp_dir / relative_path
            if not source.exists():
                continue
            destination = self.base_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def _launch_main_script(self):
        candidate_paths = [self.base_dir / "main.py", self.base_dir / "ui.py"]
        entrypoint = next((path for path in candidate_paths if path.exists() and path.stat().st_size > 0), None)
        if entrypoint is None:
            entrypoint = self.base_dir / "ui.py"

        subprocess.Popen([sys.executable, str(entrypoint)], cwd=str(self.base_dir))
        raise SystemExit(0)
