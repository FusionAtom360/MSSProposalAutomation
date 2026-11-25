import json
import logging
import shutil
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import customtkinter as ctk
from packaging.version import Version
from tkinter import messagebox

from release_artifacts import (
    REPOSITORY,
    create_backup_path,
    download_asset,
    extract_release_archive,
    preserve_local_files,
    release_assets,
    replace_directory,
    verify_release_artifact,
    version_from_release,
)


logger = logging.getLogger("mss_proposal_automation.update")


class UpdateManager:
    RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=30"

    def __init__(self):
        self.root = Path(__file__).resolve().parent.parent
        self.src = self.root / "src"
        self.window: ctk.CTk | None = None
        self.status: ctk.CTkLabel | None = None
        self.progress: ctk.CTkProgressBar | None = None
        self.release: dict[str, Any] | None = None
        self.release_version: Version | None = None
        with (self.src / "details.json").open(encoding="utf-8") as file:
            self.current = Version(json.load(file)["version"])

    def latest_release(self) -> tuple[dict[str, Any], Version] | None:
        request = urllib.request.Request(
            self.RELEASES_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": REPOSITORY,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            releases = json.load(response)
        if not isinstance(releases, list):
            raise ValueError("GitHub returned an invalid releases response")

        candidates = []
        for release in releases:
            if not isinstance(release, dict):
                raise ValueError("GitHub returned an invalid release entry")
            if release.get("draft") or not isinstance(release.get("body"), str):
                continue
            version = version_from_release(release)
            if release.get("prerelease") is not version.is_prerelease:
                raise ValueError("GitHub release channel does not match its version")
            if version > self.current:
                release_assets(release)
                candidates.append((release, version))
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[1])

    def update(self):
        if self.release is None or self.release_version is None:
            raise RuntimeError("No verified release was selected")

        assets = release_assets(self.release)
        verifier = self._sigstore_executable()
        with tempfile.TemporaryDirectory(
            prefix=".mss-update-", dir=self.root
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            archive = temporary_root / assets["archive"]["name"]
            checksum = temporary_root / assets["checksum"]["name"]
            bundle = temporary_root / assets["bundle"]["name"]
            download_asset(assets["archive"], archive)
            download_asset(assets["checksum"], checksum)
            download_asset(assets["bundle"], bundle)

            tag = self.release.get("tag_name")
            if not isinstance(tag, str):
                raise ValueError("Selected release has no tag")
            manifest = verify_release_artifact(
                archive,
                checksum,
                bundle,
                verifier,
                tag,
                self.release_version,
            )

            staged_root = temporary_root / "staged"
            staged_root.mkdir()
            extract_release_archive(archive, staged_root)
            staged_src = staged_root / "src"
            if not staged_src.is_dir():
                raise ValueError("Release archive does not contain application source")

            preserve_local_files(self.src, staged_src)

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(staged_src / "requirements.txt"),
                    "-r",
                    str(staged_src / "requirements-release.txt"),
                ],
                check=True,
            )
            backup = create_backup_path(self.root)
            self._replace_source(staged_src, backup)
            logger.info(
                "Signed release installed version=%s commit=%s",
                manifest["version"],
                manifest["commit"],
            )
            if backup.exists():
                try:
                    shutil.rmtree(backup)
                except OSError:
                    logger.warning("Previous source backup retained at %s", backup)

    def _sigstore_executable(self) -> Path:
        executable = Path(sys.executable).parent / "sigstore.exe"
        if not executable.is_file():
            raise RuntimeError(
                "The Sigstore verifier is not installed. Reinstall this application "
                "using the signed-release installer before updating."
            )
        return executable

    def _replace_source(self, staged_src: Path, backup: Path) -> None:
        app_logger = logging.getLogger("mss_proposal_automation")
        handlers = list(app_logger.handlers)
        for handler in handlers:
            handler.flush()
            handler.close()
            app_logger.removeHandler(handler)

        try:
            replace_directory(self.src, staged_src, backup)
        finally:
            if handlers:
                from app_logging import configure_logging

                configure_logging(log_dir=self.src / "logs")

    def run_ui(self):
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.window = ctk.CTk()
        self.window.title("MSS Proposal Automation")
        self.window.geometry("350x160")
        self.window.resizable(False, False)

        frame = ctk.CTkFrame(self.window, corner_radius=12)
        frame.pack(fill="both", expand=True, padx=15, pady=15)
        self.status = ctk.CTkLabel(
            frame,
            text="Checking for signed updates...",
            wraplength=280,
        )
        self.status.pack(pady=(25, 15))

        self.progress = ctk.CTkProgressBar(frame)
        self.progress.pack(fill="x", padx=20, pady=10)
        self.progress.set(0)
        self.window.after(100, self.start_check)
        self.window.mainloop()

    def start_check(self):
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        threading.Thread(target=self.check_update_thread, daemon=True).start()

    def check_update_thread(self):
        try:
            latest = self.latest_release()
            if latest is not None:
                self.release, self.release_version = latest
                self.window.after(0, self.start_update)
            else:
                self.window.after(0, lambda: self.finish("Application is up to date."))
        except (
            OSError,
            urllib.error.URLError,
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
        ) as error:
            logger.exception("Signed release check failed")
            error_message = (
                f"Update check failed:\n"
                f"{type(error).__name__}: {error}\n\n"
                f"{traceback.format_exc()}"
            )
            self.window.after(0, lambda message=error_message: self.finish(message))

    def start_update(self):
        version = self.release_version
        if version is None:
            self.finish("Update failed: no release version was selected.")
            return
        if not messagebox.askyesno(
            "Update available",
            f"Install signed version {version}?\n\n"
            "The release will be verified before application files are changed.",
            parent=self.window,
        ):
            self.finish("Update skipped.")
            return

        self.status.configure(text=f"Verifying and downloading {version}...")
        threading.Thread(target=self.update_thread, daemon=True).start()

    def update_thread(self):
        try:
            self.update()
            self.window.after(0, lambda: self.finish("Update complete."))
        except (
            OSError,
            urllib.error.URLError,
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
            subprocess.CalledProcessError,
        ) as error:
            logger.exception("Signed release update failed")
            error_message = (
                f"Update failed:\n"
                f"{type(error).__name__}: {error}\n\n"
                f"{traceback.format_exc()}"
            )
            self.window.after(0, lambda message=error_message: self.finish(message))

    def finish(self, message):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1)
        self.status.configure(text=message)
        self.window.after(100, self.window.destroy)
