import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import venv
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import customtkinter as ctk


class UpdateManager:
    REPO_OWNER = "FusionAtom360"
    REPO_NAME = "MSSProposalAutomation"
    REPO_BRANCH = "main"
    REPO_RAW_BASE_URL = (
        f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{REPO_BRANCH}"
    )
    REPO_TREE_URL = (
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/git/trees/{REPO_BRANCH}?recursive=1"
    )
    FILES_TO_EXCLUDE = {".gitignore", "update.py", ".env"}
    VENV_DIR_NAME = ".venv"

    def __init__(self, current_version=None, latest_version=None):
        self.base_dir = Path(__file__).resolve().parent
        self.project_root = self.base_dir.parent
        self.details_path = self.base_dir / "details.json"

        with self.details_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

        self.current_version = current_version or data.get("version", "0.0.0")
        self.latest_version = latest_version or self._fetch_latest_version()

    @staticmethod
    def _fetch_json(url):
        request = Request(url, headers={"User-Agent": "MSSProposalAutomation-Updater"})
        with urlopen(request, timeout=15) as response:
            return json.load(response)

    def _fetch_latest_version(self):
        try:
            data = self._fetch_json(f"{self.REPO_RAW_BASE_URL}/src/details.json")
            return data.get("version", self.current_version)
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            return self.current_version

    def _fetch_remote_paths(self):
        try:
            tree = self._fetch_json(self.REPO_TREE_URL).get("tree", [])
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            return []

        remote_paths = []
        for entry in tree:
            if entry.get("type") != "blob":
                continue

            path = entry.get("path", "")
            if not path.startswith("src/"):
                continue

            relative_path = Path(path).relative_to("src")
            if relative_path.name in self.FILES_TO_EXCLUDE:
                continue

            remote_paths.append(relative_path)

        return remote_paths

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
        if not self.check_for_update():
            return False

        window, status_label, progress_bar = self._build_update_window()
        update_state = {"error": None}

        def worker():
            try:
                with tempfile.TemporaryDirectory(prefix="mss_update_", dir=str(self.base_dir)) as temp_dir_name:
                    temp_dir = Path(temp_dir_name)
                    self._set_update_status(window, status_label, "Downloading update files...")
                    self._download_files(temp_dir)
                    self._set_update_status(window, status_label, "Replacing local files...")
                    self._replace_files(temp_dir)
                    self._set_update_status(window, status_label, "Creating virtual environment...")
                    python_executable = self._ensure_virtual_environment()
                    self._set_update_status(window, status_label, "Installing requirements...")
                    self._install_requirements(python_executable)
                    self._set_update_status(window, status_label, "Launching application...")
                    self._launch_main_script(python_executable)
            except Exception as exc:  # noqa: BLE001
                update_state["error"] = exc
                window.after(
                    0,
                    lambda error=exc: self._show_update_error(
                        window, status_label, progress_bar, error
                    ),
                )
            else:
                window.after(0, window.destroy)

        threading.Thread(target=worker, daemon=True).start()

        try:
            window.mainloop()
        finally:
            if update_state["error"] is not None:
                raise RuntimeError(f"Update failed: {update_state['error']}") from update_state["error"]

        return True

    def _build_update_window(self):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        window = ctk.CTk()
        window.title("MSS Proposal Automation")
        window.geometry("320x150")
        window.resizable(False, False)
        window.attributes("-topmost", True)

        frame = ctk.CTkFrame(window, corner_radius=16)
        frame.pack(fill="both", expand=True, padx=16, pady=16)

        title_label = ctk.CTkLabel(
            frame,
            text="Updating",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title_label.pack(pady=(18, 6))

        status_label = ctk.CTkLabel(
            frame,
            text="Checking for the latest files...",
            wraplength=240,
        )
        status_label.pack(pady=(0, 12))

        progress_bar = ctk.CTkProgressBar(frame)
        progress_bar.pack(fill="x", padx=18, pady=(0, 18))
        progress_bar.configure(mode="indeterminate")
        progress_bar.start()

        return window, status_label, progress_bar

    @staticmethod
    def _set_update_status(window, status_label, message):
        window.after(0, lambda: status_label.configure(text=message))

    @staticmethod
    def _show_update_error(window, status_label, progress_bar, error):
        progress_bar.stop()
        status_label.configure(text=f"Update failed: {error}")
        window.after(3500, window.destroy)

    def _get_files_to_update(self):
        return self._fetch_remote_paths()

    def _clear_source_tree(self):
        for path in sorted(self.base_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.name in self.FILES_TO_EXCLUDE:
                continue

            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def _download_files(self, temp_dir):
        for relative_path in self._get_files_to_update():
            remote_url = f"{self.REPO_RAW_BASE_URL}/src/{relative_path.as_posix()}"
            destination = temp_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                with urlopen(remote_url, timeout=15) as response:
                    destination.write_bytes(response.read())
            except (URLError, HTTPError, TimeoutError):
                raise RuntimeError(f"Failed to download {remote_url}")

    def _replace_files(self, temp_dir):
        self._clear_source_tree()

        for relative_path in self._get_files_to_update():
            source = temp_dir / relative_path
            if not source.exists():
                continue
            destination = self.base_dir / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    def _venv_python_path(self):
        if os.name == "nt":
            return self.project_root / self.VENV_DIR_NAME / "Scripts" / "python.exe"
        return self.project_root / self.VENV_DIR_NAME / "bin" / "python"

    def _ensure_virtual_environment(self):
        python_executable = self._venv_python_path()
        if not python_executable.exists():
            builder = venv.EnvBuilder(with_pip=True)
            builder.create(self.project_root / self.VENV_DIR_NAME)

        if not python_executable.exists():
            raise RuntimeError("Failed to create the project virtual environment.")

        return python_executable

    def _install_requirements(self, python_executable):
        requirements_path = self.base_dir / "requirements.txt"
        if not requirements_path.exists():
            raise RuntimeError(f"Missing requirements file: {requirements_path}")

        subprocess.run(
            [str(python_executable), "-m", "pip", "install", "-r", str(requirements_path)],
            cwd=str(self.project_root),
            check=True,
        )

    def _launch_main_script(self, python_executable):
        entrypoint = self.project_root / "src" / "main.py"
        if not entrypoint.exists():
            entrypoint = self.project_root / "src" / "ui.py"

        subprocess.Popen([str(python_executable), str(entrypoint)], cwd=str(self.project_root))
        raise SystemExit(0)
