from __future__ import annotations

import os
import shutil
import win32com.client as win32
from pathlib import Path
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlparse
from openpyxl import load_workbook
from docx import Document
import docx2pdf
from pypdf import PdfWriter
from scraper import Scraper
from data import DataManager
from settings import SettingsManager


class OfficeDocumentManager:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.templates_dir = self.base_dir / "templates"
        self.documents_dir = self.base_dir / "documents"
        self.alias_mapping = {}

    def complete_pricing_spreadsheet(self, data: DataManager, variables) -> Path:

        variables.update(data)
        workbook = load_workbook(data.files.pricing_spreadsheet_template)

        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        for placeholder, replacement in variables.get_all().items():
                            if placeholder in str(cell.value):
                                try:
                                    int(replacement)
                                    cell.value = int(
                                        cell.value.replace(
                                            placeholder, str(replacement)
                                        )
                                    )
                                except ValueError:
                                    cell.value = cell.value.replace(
                                        placeholder, str(replacement)
                                    )

        sheet = workbook["Edit Variables"]
        for key, value in variables.get_all().items():
            sheet.append([key, value])

        workbook.save(data.files.pricing_spreadsheet)
        return data.files.pricing_spreadsheet

    def complete_cover_letter(self, data: DataManager, variables) -> Path:
        data.update_from_pricing_spreadsheet(self.get_cell_value)
        variables.update(data)
        document = Document(str(data.files.cover_letter_template))

        for paragraph in document.paragraphs:
            self._replace_in_paragraph(paragraph, variables.get_all())

        document.save(str(data.files.cover_letter_docx))
        return data.files.cover_letter_docx

    def finalize_proposal(self, data: DataManager, scraper: Scraper) -> Path:
        docx2pdf.convert(
            str(data.files.cover_letter_docx), str(data.files.cover_letter_pdf)
        )

        writer = PdfWriter()
        writer.append(str(data.files.cover_letter_pdf))
        writer.append(str(data.files.solargraf_proposal))

        data.files.specsheets_folder.mkdir(parents=True, exist_ok=True)

        if data.system.type == 0:
            scraper.download(
                data.system.panel.specsheet_url, output_dir=data.files.specsheets_folder
            )
            scraper.download(
                data.system.inverter.specsheet_url,
                output_dir=data.files.specsheets_folder,
            )
        if data.system.type == 1:
            scraper.download(
                data.system.battery.specsheet_url,
                output_dir=data.files.specsheets_folder,
            )
        if data.system.type == 2:
            scraper.download(
                data.system.panel.specsheet_url, output_dir=data.files.specsheets_folder
            )
            scraper.download(
                data.system.inverter.specsheet_url,
                output_dir=data.files.specsheets_folder,
            )
            scraper.download(
                data.system.battery.specsheet_url,
                output_dir=data.files.specsheets_folder,
            )

        for specsheet_file in data.files.specsheets_folder.glob("*.pdf"):
            writer.append(str(specsheet_file))
        writer.write(str(data.files.final_proposal))
        return data.files.final_proposal

    def generate_email(self, data: DataManager, variables) -> None:
        data.update_from_pricing_spreadsheet(self.get_cell_value)
        variables.update(data)

        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0: olMailItem
        mail.Subject = (
            f"Mid-State Solar - Proposal for {variables.resolve(r'{{SYSTEM_TYPE}}')}"
        )
        mail.To = variables.resolve(r"{{CUSTOMER_EMAIL}}")

        email_body = data.files.email_template.read_text(encoding="utf-8")
        for placeholder, replacement in variables.get_all().items():
            email_body = email_body.replace(str(placeholder), str(replacement))

        mail.HtmlBody = email_body
        mail.Attachments.Add(str(data.files.final_proposal))
        mail.Display(False)

    @staticmethod
    def _replace_in_paragraph(paragraph: Any, replacements: Mapping[str, Any]) -> None:
        if not paragraph.runs:
            return

        original = "".join(run.text for run in paragraph.runs)
        updated = original
        for key, value in replacements.items():
            updated = updated.replace(str(key), str(value))

        if updated != original:
            paragraph.runs[0].text = updated
            for run in paragraph.runs[1:]:
                run.text = ""

    @staticmethod
    def get_cell_value(data: DataManager, sheet_name: str, cell_ref: str) -> int:
        for _ in (
            data.files.project_folder.iterdir()
            if data.files.project_folder.exists()
            else []
        ):
            if data.files.pricing_spreadsheet.exists():
                try:
                    wb = load_workbook(
                        data.files.pricing_spreadsheet, data_only=True, read_only=True
                    )
                    if sheet_name in wb.sheetnames:
                        sheet = wb[sheet_name]
                        cell = sheet[cell_ref]
                        return int(cell.value) if cell.value is not None else 0
                except Exception:
                    return 0
        return 0

    def copy_to_fileserver(self, data: DataManager, settings: SettingsManager) -> Path:
        if not settings.files.bids_folder:
            raise ValueError("FILESERVER_BIDS_FOLDER environment variable is not set.")

        destination_folder = (
            Path(settings.files.bids_folder)
            / f"{data.client.last_name}, {data.client.first_name}"
        )
        destination_folder.mkdir(parents=True, exist_ok=True)

        shutil.copy(
            data.files.final_proposal,
            destination_folder
            / f"{datetime.now().strftime('%y_%m%d')} {data.client.last_name}, {data.client.first_name} {"PV" if data.system.type == 0 else "ESS" if data.system.type == 1 else "PV ESS"} Proposal.pdf",
        )
        shutil.copy(
            data.files.pricing_spreadsheet,
            destination_folder
            / f"{datetime.now().strftime('%y_%m%d')} {data.client.last_name}, {data.client.first_name} {"PV" if data.system.type == 0 else "ESS" if data.system.type == 1 else "PV ESS"} Bid.xlsx",
        )
        shutil.copy(
            data.files.cover_letter_docx,
            destination_folder
            / f"PV ESS Proposal - {data.client.last_name}, {data.client.first_name}.docx",
        )
        shutil.copy(
            data.files.solargraf_proposal,
            destination_folder / f"Proposal for - {data.client.name}.pdf",
        )
        shutil.copytree(
            data.files.images_folder, destination_folder / "images", dirs_exist_ok=True
        )

        return destination_folder
