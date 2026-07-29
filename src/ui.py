import os
import threading
import traceback
import webbrowser
import json

import customtkinter as ctk
from tkinter import messagebox

from scraper import Scraper
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
        self.templates = TemplateManager(self.data)

        self.scraper = Scraper()
        self.office = OfficeDocumentManager()
        with open("./src/details.json", "r", encoding="utf-8") as f:
            self.version = json.load(f).get("version", "0.0.0")

        self._busy = False
        self._action_buttons = {}
        self._completed_actions = set()

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

        subtitle = ctk.CTkLabel(
            sidebar,
            text=f"v{self.version}",
            font=ctk.CTkFont(size=14),
        )
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        actions_frame = ctk.CTkScrollableFrame(
            sidebar, corner_radius=14, label_text="Actions"
        )
        actions_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="nsew")
        actions_frame.grid_columnconfigure(0, weight=1)

        button_specs = [
            ("Load Project from Solargraf", self.load_project_from_solargraf),
            ("Open Images Folder", self.open_images_folder),
            ("Open Project in Solargraf", self.open_project_in_solargraf),
            ("Open Pricing Spreadsheet", self.open_pricing_spreadsheet),
            ("Update Project Data", self.update_project_data),
            ("Download Proposal Document", self.download_proposal_document),
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
            self._action_buttons[command.__name__] = {
                "button": button,
                "text": label,
            }

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

        for index, button_data in enumerate(self._action_buttons.values()):
            button = button_data["button"]

            if index == 0:
                button.configure(state="disabled" if busy else "normal")
            else:
                button.configure(
                    state=("disabled" if busy or not self.data.project.id else "normal")
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
            ) as exc:
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

        self._completed_actions.add(task_name)
        self._update_button_status(task_name)

        if task_name == "load_project_from_solargraf":
            return

        if result:
            self._set_status(result)
        else:
            self._set_status(
                f"{task_name.replace('_', ' ').capitalize()} complete."
            )

    def _update_button_status(self, task_name):
        button_data = self._action_buttons.get(task_name)

        if not button_data:
            return

        button_data["button"].configure(
            fg_color="#2FA572", hover_color="#106A43"
        )

    def _handle_task_error(self, task_name, exc):
        self._set_busy(False)
        message = f"{task_name.replace('_', ' ').capitalize()} failed: {exc} {traceback.format_exc()}"
        self._set_status(message)
        messagebox.showerror("MSS Proposal Automation", message)

    def _require_project(self):
        if self.data == {} or self.data.project.id == 0:
            raise RuntimeError("Load a project from SolarGraf first.")

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
            text=str(self.data.project.id or "Not loaded")
        )
        if self.data.system.pv_size == 0:
            size_text = "Not loaded"
        else:
            size_text = f"{self.data.system.pv_size:g} kW"
        self.summary_labels["size_kw"].configure(text=size_text)

    def _mark_project_loaded(self):
        customer_name = self.data.client.name or "Unknown customer"
        address = self.data.client.address.street or "Address not available"
        self.project_title.configure(text=customer_name)
        self.project_hint.configure(text=f"{address}")
        self._update_summary()
        self._set_busy(False)
        self._set_status(f"Loaded {customer_name} ({self.data.project.id}).")

    def _select_project_dialog(self, projects: list[DataManager]) -> DataManager:
        if not projects:
            return DataManager()

        dialog = ctk.CTkToplevel(self)
        dialog.title("Select SolarGraf Project")
        dialog.geometry("550x450")
        dialog.grab_set()
        dialog.resizable(False, False)

        selected = {"project": DataManager()}
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)
        title = ctk.CTkLabel(
            dialog,
            text="Select a project to load",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10))
        project_names = []
        for project in projects:
            name = project.client.name or "Unknown Customer"
            project_id = project.project.id or "No ID"

            project_names.append(f"{name}  |  Project #{project_id}")

        selected_index = {"value": 0}
        list_frame = ctk.CTkScrollableFrame(dialog)
        list_frame.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        buttons = []

        def select(index):
            selected_index["value"] = index
            for button in buttons:
                button.configure(fg_color="transparent")
            buttons[index].configure(fg_color=("gray75", "gray25"))

        for index, name in enumerate(project_names):

            button = ctk.CTkButton(
                list_frame,
                text=name,
                anchor="w",
                command=lambda i=index: select(i),
            )
            button.grid(row=index, column=0, padx=5, pady=5, sticky="ew")
            buttons.append(button)
        select(0)

        def confirm():
            selected["project"] = projects[selected_index["value"]]
            dialog.destroy()

        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=2, column=0, padx=20, pady=15, sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=dialog.destroy,
        ).grid(row=0, column=0, padx=5, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="Load Project",
            command=confirm,
        ).grid(row=0, column=1, padx=5, sticky="ew")

        self.wait_window(dialog)

        return selected["project"]

    def load_project_from_solargraf(self):
        projects_data = self.scraper.get_projects(self.settings)
        if not projects_data:
            raise RuntimeError("No SolarGraf projects found.")
        selected_project = self._select_project_dialog(projects_data)
        if not selected_project:
            return "Project selection cancelled."
        payload = self.scraper.get_project_data(selected_project, self.settings)
        if not payload:
            raise RuntimeError("Failed to retrieve project data.")
        self.data.load_json(payload)
        self.templates.update(self.data)
        if self.data.project.id == 0:
            raise RuntimeError("SolarGraf payload did not include a project ID.")
        self.after(0, self._mark_project_loaded)
        return f"Loaded project {self.data.project.id}."

    def open_images_folder(self):
        self._require_project()
        os.startfile(self.data.files.images_folder)
        return f"Opened images folder for project {self.data.project.id}."

    def open_project_in_solargraf(self):
        self._require_project()
        webbrowser.open(f"https://app.solargraf.com/projects/{self.data.project.id}")
        return f"Opened SolarGraf project {self.data.project.id}."

    def update_project_data(self):
        self._require_project()
        payload = self.scraper.get_project_data(self.data, self.settings)
        if not payload:
            raise RuntimeError("Failed to fetch project data.")
        self._mark_project_loaded()
        return f"Updated project data for {self.data.project.id}."

    def download_proposal_document(self):
        self._require_project()
        output_path = self.scraper.get_proposal_document(self.data)
        return f"Downloaded proposal document to {output_path}."

    def open_pricing_spreadsheet(self):
        self._require_project()
        self.office.complete_pricing_spreadsheet(self.data, self.templates)
        os.startfile(self.data.files.pricing_spreadsheet)
        return f"Generated and opened pricing spreadsheet {self.data.files.pricing_spreadsheet}."

    def generate_cover_letter(self):
        self._require_project()
        self.office.complete_cover_letter(self.data, self.templates)
        os.startfile(self.data.files.cover_letter_docx)
        return (
            f"Generated and opened cover letter at {self.data.files.cover_letter_docx}."
        )

    def finalize_proposal_document(self):
        self._require_project()
        self.office.finalize_proposal(self.data, self.scraper)
        os.startfile(self.data.files.final_proposal)
        return f"Final proposal document created at {self.data.files.final_proposal}."

    def draft_email_to_customer(self):
        self._require_project()
        self.office.generate_email(self.data, self.templates)
        return f"Drafted email to customer with proposal attached."

    def copy_to_fileserver(self):
        self._require_project()
        self.office.copy_to_fileserver(self.data, self.settings)
        return f"Copied project {self.data.project.id} to {self.settings.files.bids_folder}."


if __name__ == "__main__":
    app = App()
    app.mainloop()
