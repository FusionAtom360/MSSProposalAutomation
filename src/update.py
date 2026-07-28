import json
import urllib.request
from pathlib import Path
import shutil
import tempfile
import threading
import customtkinter as ctk
import traceback

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
            if "." not in path:
                continue
            rel = path[4:].replace("\\", "/")
            if rel in self.EXCLUDE:
                continue
            files.append(rel)
        return files

    def update(self):
        files = self.download_tree()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for file in files:
                url = f"{self.RAW}/src/{file}"
                print(url)
                data = urllib.request.urlopen(url).read()
                target = tmp / file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

            for file in files:
                src = tmp / file
                dst = self.src / file
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                
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
            text="Checking for updates...",
            wraplength=280
        )
        self.status.pack(pady=(25, 15))

        self.progress = ctk.CTkProgressBar(frame)
        self.progress.pack(fill="x", padx=20, pady=10)
        self.progress.set(0)

        # Automatically start check after UI loads
        self.window.after(100, self.start_check)

        self.window.mainloop()


    def start_check(self):
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        threading.Thread(
            target=self.check_update_thread,
            daemon=True
        ).start()


    def check_update_thread(self):
        try:
            if self.update_available():
                self.window.after(
                    0,
                    self.start_update
                )
            else:
                self.window.after(
                    0,
                    lambda: self.finish(
                        "Application is up to date."
                    )
                )

        except Exception as e:
            error_message = (
                f"Update failed:\n"
                f"{type(e).__name__}: {e}\n\n"
                f"{traceback.format_exc()}"
            )
            

            self.window.after(
                0,
                lambda msg=error_message: self.finish(msg)
            )


    def start_update(self):
        self.status.configure(
            text="Downloading update..."
        )

        threading.Thread(
            target=self.update_thread,
            daemon=True
        ).start()


    def update_thread(self):
        try:
            self.update()

            self.window.after(
                0,
                lambda: self.finish(
                    "Update complete."
                )
            )

        except Exception as e:
            error_message = (
                f"Update failed:\n"
                f"{type(e).__name__}: {e}\n\n"
                f"{traceback.format_exc()}"
            )

            self.window.after(
                0,
                lambda msg=error_message: self.finish(msg)
            )


    def finish(self, message):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1)

        self.status.configure(
            text=message
        )

        # Close automatically after success
        self.window.after(
            100,
            self.window.destroy
        )
