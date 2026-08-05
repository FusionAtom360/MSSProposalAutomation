import os
import threading
import traceback
import webbrowser
import json
from pathlib import Path

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
        self._action_order = []
        self._last_button_states = {}
        self._last_chip_style = None
        self._last_status_message = None

        self._build_layout()

    def _build_layout(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(self, corner_radius=18)
        shell.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(shell, corner_radius=14)
        header.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="MSS Proposal Automation",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text=f"v{self.version}",
            font=ctk.CTkFont(size=13),
            text_color=("#5b6472", "#b9c1cd"),
        )
        subtitle.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        header_right = ctk.CTkFrame(header, fg_color="transparent")
        header_right.grid(row=0, column=1, rowspan=2, padx=16, pady=12, sticky="ne")
        header_right.grid_columnconfigure(0, weight=1)

        self.state_chip = ctk.CTkLabel(
            header_right,
            text="IDLE",
            width=90,
            corner_radius=10,
            fg_color=("#DBE4F0", "#2A3442"),
            text_color=("#203047", "#D4E2F9"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.state_chip.grid(row=0, column=0, padx=0, pady=(0, 8), sticky="e")

        quick = ctk.CTkFrame(header_right)
        quick.grid(row=1, column=0, padx=0, pady=0, sticky="e")
        for col in range(4):
            quick.grid_columnconfigure(col, weight=1)

        quick_buttons = [
            ("Settings", self.open_settings),
            ("Pricing Template", self.open_pricing_template),
            ("Cover Template", self.open_cover_template),
            ("Email Template", self.open_email_template),
        ]
        for index, (label, command) in enumerate(quick_buttons):
            ctk.CTkButton(
                quick,
                text=label,
                width=116,
                height=30,
                font=ctk.CTkFont(size=12),
                command=lambda fn=command: self._run_task(fn),
            ).grid(row=0, column=index, padx=3, pady=0, sticky="ew")

        body = ctk.CTkFrame(shell, corner_radius=14)
        body.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="nsew")
        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        workflow = ctk.CTkFrame(body, corner_radius=12)
        workflow.grid(row=0, column=0, padx=20, pady=12, sticky="nsew")
        workflow.grid_columnconfigure(0, weight=1)

        section_specs = [
            (
                "Setup",
                [
                    ("Create Project in Solargraf", self.create_project_in_solargraf),
                    ("Load Project from Solargraf", self.load_project_from_solargraf),
                ],
            ),
            (
                "Project",
                [
                    ("Open Images Folder", self.open_images_folder),
                    ("Open Project in Solargraf", self.open_project_in_solargraf),
                    ("Update Project from Solargraf", self.update_project_data),
                ],
            ),
            (
                "Documents",
                [
                    ("Open Pricing Spreadsheet", self.open_pricing_spreadsheet),
                    ("Download Proposal Document", self.download_proposal_document),
                    ("Generate Cover Letter", self.generate_cover_letter),
                    ("Finalize Proposal", self.finalize_proposal),
                ],
            ),
        ]

        row = 0
        for section_title, actions in section_specs:
            ctk.CTkLabel(
                workflow,
                text=section_title,
                font=ctk.CTkFont(size=15, weight="bold"),
            ).grid(row=row, column=0, padx=12, pady=(6, 8), sticky="w")
            row += 1

            for label, command in actions:
                button = ctk.CTkButton(
                    workflow,
                    text=label,
                    command=lambda fn=command: self._run_task(fn),
                )
                button.grid(row=row, column=0, padx=12, pady=(0, 10), sticky="ew")

                command_name = command.__name__
                self._action_order.append(command_name)
                self._action_buttons[command_name] = {
                    "button": button,
                    "text": label,
                }
                if len(self._action_order) > 2:
                    button.configure(state="disabled")
                row += 1

        content = ctk.CTkFrame(body, corner_radius=12)
        content.grid(row=0, column=1, padx=(8, 12), pady=12, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)

        project_header = ctk.CTkFrame(content, corner_radius=10)
        project_header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        project_header.grid_columnconfigure(0, weight=1)

        self.project_title = ctk.CTkLabel(
            project_header,
            text="No customer loaded",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        )
        self.project_title.grid(row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        self.project_hint = ctk.CTkLabel(
            project_header,
            text="Load a SolarGraf project to begin",
            text_color=("#5b6472", "#b9c1cd"),
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.project_hint.grid(row=1, column=0, padx=14, pady=(0, 12), sticky="w")

        summary = ctk.CTkFrame(content, corner_radius=10)
        summary.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")
        summary.grid_columnconfigure((0, 1, 2), weight=1)

        self.summary_labels = {}
        summary_fields = [
            ("Project ID", "project_id"),
            ("API ID", "api_id"),
            ("Size", "size_kw"),
            ("Customer", "customer"),
            ("Utility", "utility"),
            ("System", "system_type"),
        ]

        for index, (label, key) in enumerate(summary_fields):
            row_idx = index // 3
            col_idx = index % 3
            field = ctk.CTkFrame(summary, corner_radius=8)
            field.grid(row=row_idx, column=col_idx, padx=8, pady=8, sticky="ew")
            field.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(field, text=label, text_color=("#5b6472", "#b9c1cd")).grid(
                row=0, column=0, padx=10, pady=(8, 0), sticky="w"
            )
            value_label = ctk.CTkLabel(
                field,
                text="--",
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w",
                justify="left",
                wraplength=220,
            )
            value_label.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="w")
            self.summary_labels[key] = value_label

        log_frame = ctk.CTkFrame(content, corner_radius=10)
        log_frame.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            log_frame, text="Activity Log", font=ctk.CTkFont(size=16, weight="bold")
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        self.log_box = ctk.CTkTextbox(log_frame, wrap="word")
        self.log_box.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.log_box.configure(state="disabled")

    def _set_status(self, message):
        if message == self._last_status_message:
            return
        self._last_status_message = message
        self._log(message)

    def _set_state_chip(self, state_text, busy=False):
        style = {
            "text": state_text,
            "fg_color": ("#DBE4F0", "#2A3442"),
            "text_color": ("#203047", "#D4E2F9"),
        }

        if busy:
            style = {
                "text": state_text,
                "fg_color": ("#F6DDAC", "#6D5420"),
                "text_color": ("#4A3203", "#FFF0CA"),
            }
        elif self.data.project.id:
            style = {
                "text": state_text,
                "fg_color": ("#CFEFD9", "#174B2D"),
                "text_color": ("#0D4426", "#CFF7DE"),
            }

        style_key = (style["text"], style["fg_color"], style["text_color"])
        if style_key == self._last_chip_style:
            return
        self._last_chip_style = style_key
        self.state_chip.configure(**style)

    def _log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _set_busy(self, busy):
        self._busy = busy
        self._set_state_chip("WORKING" if busy else ("READY" if self.data.project.id else "IDLE"), busy=busy)

        for index, action_name in enumerate(self._action_order):
            button_data = self._action_buttons[action_name]
            button = button_data["button"]

            if busy:
                self._set_button_state(action_name, button, "disabled")
                continue

            if index < 2:
                self._set_button_state(action_name, button, "normal")
            else:
                target_state = "normal" if self.data.project.id else "disabled"
                self._set_button_state(action_name, button, target_state)

    def _set_button_state(self, action_name, button, state):
        if self._last_button_states.get(action_name) == state:
            return
        self._last_button_states[action_name] = state
        button.configure(state=state)

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
                traceback.print_exc()
                self.after(
                    0, lambda error=exc: self._handle_task_error(task.__name__, error)
                )
            else:
                self.after(0, lambda: self._handle_task_result(task.__name__, result))

        self._set_busy(True)
        self._set_status(f"Running: {task.__name__.replace('_', ' ')}")
        threading.Thread(target=worker, daemon=True).start()

    def _handle_task_result(self, task_name, result):
        self._set_busy(False)

        self._completed_actions.add(task_name)
        self._update_button_status(task_name)

        if task_name in {"load_project_from_solargraf", "update_project_data"}:
            self._mark_project_loaded()
            if result:
                self._log(result)
            return

        if result:
            self._set_status(f"Done: {task_name.replace('_', ' ')}")
            self._log(result)
        else:
            self._set_status(f"Done: {task_name.replace('_', ' ')}")

    def _update_button_status(self, task_name):
        button_data = self._action_buttons.get(task_name)

        if not button_data:
            return

        button_data["button"].configure(
            fg_color="#174B2D", hover_color="#106A43"
        )

    def _handle_task_error(self, task_name, exc):
        self._set_busy(False)
        detail = f"{task_name.replace('_', ' ').capitalize()} failed: {exc}"
        self._set_status(f"Failed: {task_name.replace('_', ' ')}")
        self._log(f"{detail}\n{traceback.format_exc()}")
        messagebox.showerror("MSS Proposal Automation", detail)

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
            text=str(self.data.project.id or "--")
        )
        self.summary_labels["api_id"].configure(
            text=str(self.data.project.api_id or "--")
        )
        if self.data.system.pv_size == 0:
            size_text = "--"
        else:
            size_text = f"{self.data.system.pv_size:g} kW"
        self.summary_labels["size_kw"].configure(text=size_text)
        self.summary_labels["customer"].configure(text=self.data.client.name or "--")
        self.summary_labels["utility"].configure(text=self.data.utility.name or "--")

        if self.data.system.type == 0:
            system_text = "PV"
        elif self.data.system.type == 1:
            system_text = "ESS"
        elif self.data.system.type == 2:
            system_text = "PV + ESS"
        else:
            system_text = "--"
        self.summary_labels["system_type"].configure(text=system_text)

    def _mark_project_loaded(self):
        customer_name = self.data.client.name or "Unknown customer"
        address = self.data.client.address.street or "Address not available"
        self.project_title.configure(text=customer_name)
        self.project_hint.configure(text=address)
        self._update_summary()
        self._set_status(f"Loaded: {self.data.project.id}")
        self._log(f"Loaded {customer_name} ({self.data.project.id}).")

    def _select_project_dialog(self, projects: list[dict]) -> dict:
        if not projects:
            return {}

        dialog = ctk.CTkToplevel(self)
        dialog.title("Select SolarGraf Project")
        dialog.geometry("550x450")
        dialog.grab_set()
        dialog.resizable(False, False)

        selected = {"project": {}}
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
            name = project.get("name") or "Unknown Customer"
            project_id = project.get("id") or "No ID"

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

    def open_settings(self):
        if self.settings.files.settings.is_file():
            os.startfile(self.settings.files.settings)
        return f"Opened settings file at {self.settings.files.settings}."

    def _open_template(self, template_path: Path, label: str):
        if not template_path.is_file():
            raise FileNotFoundError(f"{label} template not found at {template_path}")
        os.startfile(template_path)
        return f"Opened {label} template at {template_path}."

    def open_pricing_template(self):
        template_path = self.settings.files.templates_folder / "pricing_spreadsheet.xlsx"
        return self._open_template(template_path, "pricing spreadsheet")

    def open_cover_template(self):
        if self.data.files.cover_letter_template and self.data.files.cover_letter_template.is_file():
            return self._open_template(self.data.files.cover_letter_template, "cover letter")

        candidates = sorted(self.settings.files.templates_folder.glob("cover_letter_*.docx"))
        if candidates:
            return self._open_template(candidates[0], "cover letter")

        raise FileNotFoundError("No cover letter template found in templates folder")

    def open_email_template(self):
        template_path = self.settings.files.templates_folder / "email.html"
        return self._open_template(template_path, "email")

    def create_project_in_solargraf(self):
        webbrowser.open("https://app.solargraf.com/projects/create")
        return "Opened SolarGraf project creation page in web browser."

    def load_project_from_solargraf(self):
        projects_data = self.scraper.get_projects(self.settings)
        if not projects_data:
            raise RuntimeError("No SolarGraf projects found.")
        selected_project = self._select_project_dialog(projects_data)
        if not selected_project:
            return "Project selection cancelled."
        project_api_id = str(selected_project.get("api_id") or "")
        payload = self.scraper.get_project_data(project_api_id, self.settings)
        if not payload:
            raise RuntimeError("Failed to retrieve project data.")
        self.data.load_json(payload)
        self.templates.update(self.data)
        if self.data.project.id == 0:
            raise RuntimeError("SolarGraf payload did not include a project ID.")
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
        payload = self.scraper.get_project_data(self.data.project.api_id, self.settings)
        if not payload:
            raise RuntimeError("Failed to fetch project data.")
        self.data.load_json(payload)
        self.templates.update(self.data)
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

    def finalize_proposal(self):
        self._require_project()
        self.office.finalize_proposal(self.data, self.templates, self.scraper)
        os.startfile(self.data.files.final_proposal)
        self.office.generate_email(self.data, self.templates)
        self.office.copy_to_fileserver(self.data, self.settings)
        return f"Final proposal document created at {self.data.files.final_proposal}.\nDrafted email to customer with proposal attached.\nCopied project {self.data.project.id} to {self.settings.files.bids_folder}."

if __name__ == "__main__":
    app = App()
    app.mainloop()
