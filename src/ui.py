import os
import shutil
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote
import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

from projects import ProjectManager
from solargraf import SolargrafScraper
from office import OfficeDocumentManager

from data import DataManager
from settings import SettingsManager
from template import TemplateManager

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MSS Proposal Automation")
        self.geometry("1080x720")
        self.minsize(960, 640)

        self.settings = SettingsManager()
        self.data = DataManager()
        self.templates = TemplateManager()

        self.manager = ProjectManager()
        self.scraper = SolargrafScraper()
        self.office = OfficeDocumentManager()

        self.current_payload = None
        self.current_project_id = None
        self.current_public_id = None
        self.current_proposal_id = None
        self.current_financial_id = None
        self.current_client_name = None
        self.current_address = None
        self.current_size_kw = None

        self._busy = False
        self._action_buttons = []

        self._build_layout()

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, corner_radius=18)
        sidebar.grid(row=0, column=0, padx=(20, 12), pady=20, sticky="nsew")
        sidebar.grid_rowconfigure(2, weight=1)

        title = ctk.CTkLabel(
            sidebar,
            text="MSS Proposal Automation",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 4), sticky="w")

        actions_frame = ctk.CTkScrollableFrame(
            sidebar, corner_radius=14, label_text="Actions"
        )
        actions_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        actions_frame.grid_columnconfigure(0, weight=1)

        button_specs = [
            ("Load Project from SolarGraf", self.load_project_from_solargraf),
            ("Open Images Folder", self.open_images_folder),
            ("Open Project in SolarGraf", self.open_project_in_solargraf),
            ("Update Project Data", self.update_project_data),
            ("Download Proposal Document", self.download_proposal_document),
            ("Open Pricing Spreadsheet", self.open_pricing_spreadsheet),
            ("Generate Cover Letter", self.generate_cover_letter),
            ("Finalize Proposal Document", self.finalize_proposal_document),
            ("Draft Email to Customer", self.draft_email_to_customer),
            ("Copy to FileServer", self.copy_to_fileserver),
        ]

        for row, (label, command) in enumerate(button_specs):
            button = ctk.CTkButton(
                actions_frame, text=label, command=lambda fn=command: self._run_task(fn)
            )
            button.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
            if row > 0:
                button.configure(state="disabled")
            self._action_buttons.append(button)

        self.status_label = ctk.CTkLabel(
            sidebar,
            text="",
            justify="left",
            wraplength=280,
            anchor="w",
        )
        self.status_label.grid(row=3, column=0, padx=20, pady=(0, 18), sticky="ew")

        content = ctk.CTkFrame(self, corner_radius=18)
        content.grid(row=0, column=1, padx=(12, 20), pady=20, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(content, corner_radius=14)
        header.grid(row=0, column=0, padx=18, pady=(18, 12), sticky="ew")
        header.grid_columnconfigure((0, 1), weight=1)

        self.project_title = ctk.CTkLabel(
            header,
            text="No customer loaded",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        self.project_title.grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        self.project_hint = ctk.CTkLabel(
            header,
            text="",
            text_color=("#5b6472", "#b9c1cd"),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.project_hint.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")

        summary = ctk.CTkFrame(content, corner_radius=14)
        summary.grid(row=1, column=0, padx=18, pady=(0, 12), sticky="ew")
        summary.grid_columnconfigure((0, 1), weight=1)

        self.summary_labels = {}
        summary_fields = [
            ("Project ID", "project_id"),
            ("Size (kW)", "size_kw"),
        ]

        for index, (label, key) in enumerate(summary_fields):
            row = 0
            column = index
            field = ctk.CTkFrame(summary, corner_radius=10)
            field.grid(row=row, column=column, padx=12, pady=12, sticky="ew")
            field.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(field, text=label, text_color=("#5b6472", "#b9c1cd")).grid(
                row=0, column=0, padx=12, pady=(10, 0), sticky="w"
            )
            value_label = ctk.CTkLabel(
                field,
                text="Not loaded",
                font=ctk.CTkFont(size=16, weight="bold"),
                anchor="w",
                justify="left",
                wraplength=240,
            )
            value_label.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")
            self.summary_labels[key] = value_label

        log_frame = ctk.CTkFrame(content, corner_radius=14)
        log_frame.grid(row=2, column=0, padx=18, pady=(0, 18), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_frame, text="Activity Log", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        self.log_box = ctk.CTkTextbox(log_frame, wrap="word")
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.log_box.configure(state="disabled")

    def _set_status(self, message):
        self.status_label.configure(text=message)
        self._log(message)

    def _log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_busy(self, busy):
        self._busy = busy
        for index, button in enumerate(self._action_buttons):
            if index == 0:
                button.configure(state="disabled" if busy else "normal")
            else:
                button.configure(
                    state=(
                        "disabled" if busy or self.current_payload is None else "normal"
                    )
                )

    def _run_task(self, task):
        if self._busy:
            return

        def worker():
            try:
                result = task()
            except (
                RuntimeError,
                FileNotFoundError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
            ) as exc:  # noqa: BLE001
                self.after(
                    0, lambda error=exc: self._handle_task_error(task.__name__, error)
                )
            else:
                self.after(0, lambda: self._handle_task_result(task.__name__, result))

        self._set_busy(True)
        self._set_status(f"Running {task.__name__.replace('_', ' ')}...")
        threading.Thread(target=worker, daemon=True).start()

    def _handle_task_result(self, task_name, result):
        self._set_busy(False)
        if task_name == "load_project_from_solargraf":
            return
        if result:
            self._set_status(result)
        else:
            self._set_status(f"{task_name.replace('_', ' ').capitalize()} complete.")

    def _handle_task_error(self, task_name, exc):
        self._set_busy(False)
        message = f"{task_name.replace('_', ' ').capitalize()} failed: {exc}"
        self._set_status(message)
        messagebox.showerror("MSS Proposal Automation", message)

    def _require_project(self):
        if not self.current_payload or self.current_project_id is None:
            raise RuntimeError("Load a project from SolarGraf first.")

    def _project_folder(self):
        self._require_project()
        return self.manager.projects_dir / str(self.current_project_id)

    def _project_documents_folder(self):
        return self._project_folder() / "documents"

    def _open_path(self, path):
        resolved_path = Path(path)
        if not resolved_path.exists():
            raise FileNotFoundError(f"{resolved_path} does not exist.")
        os.startfile(resolved_path)

    def _find_first_matching_file(self, folder, patterns):
        folder_path = Path(folder)
        for pattern in patterns:
            matches = sorted(folder_path.rglob(pattern))
            if matches:
                return matches[0]
        return None

    def _find_value(self, payload, target_keys):
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key in target_keys and value not in (None, ""):
                    return value
                found = self._find_value(value, target_keys)
                if found not in (None, ""):
                    return found
        elif isinstance(payload, list):
            for value in payload:
                found = self._find_value(value, target_keys)
                if found not in (None, ""):
                    return found
        return None

    def _update_summary(self):
        self.summary_labels["project_id"].configure(
            text=str(self.current_project_id or "Not loaded")
        )
        if self.current_size_kw is None:
            size_text = "Not loaded"
        else:
            size_text = f"{self.current_size_kw:g} kW"
        self.summary_labels["size_kw"].configure(text=size_text)

    def _mark_project_loaded(self):
        customer_name = self.current_client_name or "Unknown customer"
        address = self.current_address or "Address not available"
        self.project_title.configure(text=customer_name)
        self.project_hint.configure(text=f"{address}")
        self._update_summary()
        self._set_busy(False)
        self._set_status(f"Loaded {customer_name} ({self.current_project_id}).")

    def load_project_from_solargraf(self):
        payload = self.scraper.get_project_data()
        project_id = self.manager.create_project_from_json(payload)
        if project_id is None:
            raise RuntimeError("SolarGraf payload did not include a project ID.")

        self.current_payload = payload
        self.current_project_id = str(project_id)
        self.current_public_id = payload.get("public_id") or self._find_value(
            payload, {"public_id"}
        )
        self.current_client_name = payload.get("client_name") or self._find_value(
            payload, {"client_name"}
        )
        self.current_address = payload.get("address") or self._find_value(
            payload, {"address"}
        )

        pricing = (
            payload.get("Settings", {}).get("Pricing", {})
            if isinstance(payload, dict)
            else {}
        )
        project_connection = (
            pricing.get("ProjectConnection", {}) if isinstance(pricing, dict) else {}
        )
        financial_options = (
            pricing.get("FinancialOptions", []) if isinstance(pricing, dict) else []
        )
        proposals = payload.get("proposals", []) if isinstance(payload, dict) else []

        self.current_proposal_id = (
            project_connection.get("proposal_id")
            if isinstance(project_connection, dict)
            else None
        )
        self.current_financial_id = None
        if isinstance(financial_options, list) and financial_options:
            first_option = financial_options[0]
            if isinstance(first_option, dict):
                self.current_financial_id = first_option.get("id")

        self.current_size_kw = None
        if isinstance(proposals, list) and proposals:
            first_proposal = proposals[0]
            if isinstance(first_proposal, dict):
                self.current_size_kw = first_proposal.get("sizeInKw")

        self.after(0, self._mark_project_loaded)
        return None

    def open_images_folder(self):
        self._require_project()
        self.manager.open_images_folder(self.current_project_id)
        return f"Opened images folder for project {self.current_project_id}."

    def open_project_in_solargraf(self):
        self._require_project()
        webbrowser.open(f"https://app.solargraf.com/projects/{self.current_project_id}")
        return f"Opened SolarGraf project {self.current_project_id}."

    def update_project_data(self):
        self._require_project()
        payload = self.scraper.get_project_data(
            project_id=self.current_project_id, public_id=self.current_public_id
        )
        if not payload:
            raise RuntimeError("Failed to fetch project data.")
        self.current_payload = payload
        self.manager.update_project_data(self.current_project_id, payload)
        self.current_public_id = payload.get("public_id") or self._find_value(
            payload, {"public_id"}
        )
        self.current_client_name = payload.get("client_name") or self._find_value(
            payload, {"client_name"}
        )
        self.current_address = payload.get("address") or self._find_value(
            payload, {"address"}
        )

        pricing = (
            payload.get("Settings", {}).get("Pricing", {})
            if isinstance(payload, dict)
            else {}
        )
        project_connection = (
            pricing.get("ProjectConnection", {}) if isinstance(pricing, dict) else {}
        )
        financial_options = (
            pricing.get("FinancialOptions", []) if isinstance(pricing, dict) else []
        )
        proposals = payload.get("proposals", []) if isinstance(payload, dict) else []

        self.current_proposal_id = (
            project_connection.get("proposal_id")
            if isinstance(project_connection, dict)
            else None
        )
        self.current_financial_id = None
        if isinstance(financial_options, list) and financial_options:
            first_option = financial_options[0]
            if isinstance(first_option, dict):
                self.current_financial_id = first_option.get("id")

        self.current_size_kw = None
        if isinstance(proposals, list) and proposals:
            first_proposal = proposals[0]
            if isinstance(first_proposal, dict):
                self.current_size_kw = first_proposal.get("sizeInKw")

        self._mark_project_loaded()
        return f"Updated project data for {self.current_project_id}."

    def download_proposal_document(self):
        self._require_project()
        if (
            not self.current_public_id
            or not self.current_proposal_id
            or not self.current_financial_id
        ):
            raise RuntimeError(
                "Project data is missing public, proposal, or financial IDs."
            )

        output_path = self.scraper.get_proposal_document(
            str(self.current_project_id),
            str(self.current_public_id),
            str(self.current_proposal_id),
            str(self.current_financial_id),
        )
        return f"Downloaded proposal document to {output_path}."

    def open_pricing_spreadsheet(self):
        self._require_project()
        if self.current_payload is None:
            raise RuntimeError("Project data is missing.")

        spreadsheet = self.office.complete_pricing_spreadsheet(
            str(self.current_project_id),
            self.current_payload,
        )
        self._open_path(spreadsheet)
        return f"Generated and opened pricing spreadsheet {spreadsheet}."

    def generate_cover_letter(self):
        self._require_project()
        if self.current_payload is None:
            raise RuntimeError("Project data is missing.")

        destination = self.office.complete_cover_letter(
            str(self.current_project_id),
            self.current_payload,
        )
        self._open_path(destination)
        return f"Generated and opened cover letter at {destination}."

    def finalize_proposal_document(self):
        self._require_project()

        destination = self.office.finalize_proposal(
            str(self.current_project_id),
            self.current_payload,
        )

        return f"Final proposal document created at {destination}."

    def draft_email_to_customer(self):
        self._require_project()
        self.office.generate_email(
            str(self.current_project_id),
            self.current_payload,
        )
        return f"Drafted email to customer with proposal attached."

    def copy_to_fileserver(self):
        self._require_project()
        destination_folder = self.office.copy_to_fileserver(
            str(self.current_project_id),
            self.current_payload,
        )
        return f"Copied project {self.current_project_id} to {destination_folder}."


if __name__ == "__main__":
    app = App()
    app.mainloop()
