from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any, Mapping
from urllib.parse import urlparse
from openpyxl import load_workbook
from docx import Document
import docx2pdf
from pypdf import PdfWriter
from solargraf import SolargrafScraper
import os
import shutil
from dotenv import load_dotenv
import win32com.client as win32


class OfficeDocumentManager:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.templates_dir = self.base_dir / "templates"
        self.documents_dir = self.base_dir / "documents"
        self.alias_mapping = {}

    def complete_pricing_spreadsheet(
        self,
        project_id: str,
        project_data: dict,
    ) -> Path:

        template_path = self.templates_dir / "pricing_spreadsheet.xlsx"
        output_dir = Path("projects") / str(project_id) / "documents"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"pricing_spreadsheet.xlsx"

        workbook = load_workbook(template_path)
        variable_mapping = self._generate_mapping(project_data)

        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        for placeholder, replacement in variable_mapping.items():
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

        workbook.save(output_path)
        return output_path

    def complete_cover_letter(
        self,
        project_id: str,
        project_data: dict,
    ) -> Path:

        variable_mapping = self._generate_mapping(project_data)
        if self._get_system_type(project_data) == 0:
            template_path = self.templates_dir / "cover_letter_storage_only.docx"
        elif self._get_system_type(project_data) == 1:
            template_path = self.templates_dir / "cover_letter_solar_only.docx"
        else:
            template_path = self.templates_dir / "cover_letter_solar_storage.docx"

        output_dir = Path("projects") / str(project_id) / "documents"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"cover_letter.docx"

        document = Document(str(template_path))
        variable_mapping = self._generate_mapping(project_data)

        for paragraph in document.paragraphs:
            self._replace_in_paragraph(paragraph, variable_mapping)

        document.save(str(output_path))
        return output_path

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _extract_urls(value: Any) -> list[str]:
        if isinstance(value, str):
            candidate = value.strip()
            return [candidate] if OfficeDocumentManager._is_http_url(candidate) else []

        if isinstance(value, dict):
            urls: list[str] = []
            for nested in value.values():
                urls.extend(OfficeDocumentManager._extract_urls(nested))
            return urls

        if isinstance(value, (list, tuple, set)):
            urls: list[str] = []
            for item in value:
                urls.extend(OfficeDocumentManager._extract_urls(item))
            return urls

        return []

    @staticmethod
    def _walk_project_data(
        value: Any,
        project_specsheets_dir: Path,
        scraper: SolargrafScraper,
    ) -> None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                if "spec_sheet" in str(key).lower():
                    for url in OfficeDocumentManager._extract_urls(nested_value):
                        scraper.get_spec_sheet(url, output_dir=project_specsheets_dir)

                OfficeDocumentManager._walk_project_data(
                    nested_value, project_specsheets_dir, scraper
                )
        elif isinstance(value, (list, tuple, set)):
            for item in value:
                OfficeDocumentManager._walk_project_data(
                    item, project_specsheets_dir, scraper
                )

    def finalize_proposal(self, project_id: str, project_data: dict) -> Path:

        cover_letter_path = (
            Path("projects") / str(project_id) / "documents" / "cover_letter.docx"
        )
        solargraf_proposal_path = (
            Path("projects") / str(project_id) / "documents" / "solargraf_proposal.pdf"
        )
        output_dir = Path("projects") / str(project_id) / "documents"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "cover_letter.pdf"
        combined_output_path = output_dir / "final_proposal.pdf"

        docx2pdf.convert(str(cover_letter_path), str(output_path))

        writer = PdfWriter()
        writer.append(str(output_path))
        writer.append(str(solargraf_proposal_path))

        specsheets_path = output_dir / "specsheets"
        specsheets_path.mkdir(parents=True, exist_ok=True)

        self._walk_project_data(project_data, specsheets_path, SolargrafScraper())
        for specsheet_file in specsheets_path.glob("*.pdf"):
            writer.append(str(specsheet_file))

        writer.write(str(combined_output_path))

        return combined_output_path

    def generate_email(self, project_id: str, project_data: dict) -> Path:
        variable_mapping = self._generate_mapping(project_data)
        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0: olMailItem
        mail.Subject = f"Mid-State Solar - Proposal for {variable_mapping.get(r'{{SYSTEM_TYPE}}', '')}"
        mail.To = variable_mapping.get(r"{{CUSTOMER_EMAIL}}", "")
        print(mail.To)
        template_path = self.templates_dir / "email.html"

        email_body = template_path.read_text(encoding="utf-8")
        for placeholder, replacement in variable_mapping.items():
            email_body = email_body.replace(str(placeholder), str(replacement))
        print(email_body)

        mail.HtmlBody = email_body
        proposal_path = os.path.abspath(
            str(Path("projects") / str(project_id) / "documents" / "final_proposal.pdf")
        )
        mail.Attachments.Add(proposal_path)

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

    def _generate_mapping(self, project_data: dict) -> dict[str, any]:
        mapping = {
            r"{{JOB_NAME}}": project_data["client_name"].upper(),
            r"{{CUSTOMER_NAME}}": project_data["client_name"],
            r"{{CUSTOMER_FIRST_NAME}}": project_data["client_name"].split()[0],
            r"{{CUSTOMER_LAST_NAME}}": project_data["client_name"].split()[-1],
            r"{{CUSTOMER_ADDRESS_1}}": project_data["Position"]["street"],
            r"{{CUSTOMER_ADDRESS_2}}": f"{project_data['Position']['city']}, {project_data['Position']['region_code']} {project_data['Position']['postal_code']}",
            r"{{CUSTOMER_ADDRESS_STREET}}": project_data["Position"]["street"],
            r"{{CUSTOMER_ADDRESS_CITY}}": project_data["Position"]["city"],
            r"{{CUSTOMER_ADDRESS_ZIP}}": project_data["Position"]["postal_code"],
            r"{{USAGE_JAN}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][0]["amount"],
            r"{{USAGE_FEB}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][1]["amount"],
            r"{{USAGE_MAR}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][2]["amount"],
            r"{{USAGE_APR}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][3]["amount"],
            r"{{USAGE_MAY}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][4]["amount"],
            r"{{USAGE_JUN}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][5]["amount"],
            r"{{USAGE_JUL}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][6]["amount"],
            r"{{USAGE_AUG}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][7]["amount"],
            r"{{USAGE_SEP}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][8]["amount"],
            r"{{USAGE_OCT}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][9]["amount"],
            r"{{USAGE_NOV}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][10]["amount"],
            r"{{USAGE_DEC}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
                "Bills"
            ][11]["amount"],
            r"{{PREPARED_DATE}}": datetime.now().strftime("%B %d, %Y"),
            r"{{START_YEAR}}": str(datetime.now().year),
            r"{{CUSTOMER_EMAIL}}": project_data["client_email"],
            r"{{CUSTOMER_PHONE}}": project_data["client_phone"],
            r"{{SYSTEM_TYPE}}": self._get_system_type_string(project_data),
            r"{{PANEL_STC}}": project_data["Materials"]["panel"][0]["size_in_watts"],
            # r"{{PANEL_PTC_RATIO}}": project_data["Materials"]["panel"][0]["ptc_in_watts"] / project_data["Materials"]["panel"][0]["size_in_watts"],
            r"{{PANEL_MANUFACTURER}}": project_data["Materials"]["panel"][0][
                "Manufacturer"
            ]["name"],
            r"{{PANEL_MANUFACTURER_UPPERCASE}}": project_data["Materials"]["panel"][0][
                "Manufacturer"
            ]["name"].upper(),
            r"{{INVERTER_MANUFACTURER}}": project_data["Materials"]["inverter"][0][
                "Manufacturer"
            ]["name"],
            r"{{INVERTER_MANUFACTURER_UPPERCASE}}": project_data["Materials"][
                "inverter"
            ][0]["Manufacturer"]["name"].upper(),
            r"{{ENPHASE_PLATINUM_INSTALLER}}": self._get_enphase_message(project_data),
            r"{{PV_SIZE}}": project_data["proposals"][0]["sizeInKw"],
            r"{{PANEL_QUANTITY}}": project_data["Materials"]["panel"][0]["count"],
            r"{{PV_PRICE}}": f"${self._get_pv_price(project_data):,}",
            # r"{{TOTAL_PRICE}}": f"${self._get_pv_price(project_data)+self._get_storage_price(project_data):,}",
            r"{{LOAN_PAYMENT}}": f"${self._calculate_loan_payment(project_data):,}",
            r"{{PANEL_WARRANTY}}": project_data["Materials"]["panel"][0]["warranty"],
            # r"{{INVERTER_WARRANTY}}": project_data["Materials"]["inverter"][0]["warranty"],
            r"{{BATTERY_SIZE}}": project_data["StorageSettings"][0]["minStorageReq"],
            r"{{BATTERY_COUNT}}": project_data["Materials"]["batteryBackup"][0][
                "count"
            ],
            r"{{BATTERY_MODEL}}": project_data["Materials"]["batteryBackup"][0]["name"],
            r"{{BATTERY_WARRANTY}}": project_data["Materials"]["batteryBackup"][0][
                "warranty"
            ],
            # r"{{BATTERY_WARRANTY_CYCLES}}": 6000,
            # r"{{STORAGE_PRICE}}":  f"${self._get_storage_price(project_data):,}",
            r"{{LOAN_TERM}}": os.getenv("LOAN_TERM"),
            r"{{LOAN_INTEREST_RATE}}": float(os.getenv("LOAN_INTEREST_RATE")) * 100,
            r"{{TOTAL_USAGE}}": self._get_total_usage(project_data),
            # r"{{TOTAL_SIZE}}": "
            #r"{{USAGE_PERCENTAGE}}": int(project_data["proposals"][0]["sizeInKw"] / (self._get_total_usage(project_data) / 1000) * 100),
        }
        for key, value in mapping.items():
            if value in self.alias_mapping:
                mapping[key] = self.alias_mapping[value]
        return mapping

    @staticmethod
    def _calculate_loan_payment(project_data: dict) -> float:
        return 0

    @staticmethod
    def _get_pv_price(project_data: dict) -> str:
        # Attempt to locate a generated pricing_spreadsheet.xlsx under projects/*/documents
        projects_dir = Path("projects")
        for project_folder in projects_dir.iterdir() if projects_dir.exists() else []:
            doc_path = project_folder / "documents" / "pricing_spreadsheet.xlsx"
            if doc_path.exists():
                try:
                    wb = load_workbook(doc_path, data_only=True, read_only=True)
                    if "Pricing Calculator" in wb.sheetnames:
                        sheet = wb["Pricing Calculator"]
                        cell = sheet["D88"]
                        return cell.value if cell.value is not None else ""
                except Exception:
                    return 0

        return 0

    @staticmethod
    def _get_total_usage(project_data: dict):
        return sum(
                [
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        0
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        1
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        2
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        3
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        4
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        5
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        6
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        7
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        8
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        9
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        10
                    ]["amount"],
                    project_data["Settings"]["Pricing"]["ProjectConnection"]["Bills"][
                        11
                    ]["amount"],
                ])

    @staticmethod
    def _get_enphase_message(project_data: dict) -> str:
        if (
            project_data["Materials"]["inverter"][0]["Manufacturer"]["name"].lower()
            == "enphase"
        ):
            return "Mid-State Solar is a Platinum Installer has been installing Enphase products since 2009."
        else:
            return ""

    @staticmethod
    def _get_system_type(project_data: dict) -> int:
        if project_data["is_battery_only"]:
            return 0
        elif project_data["is_roofing_only"]:
            return 1
        else:
            return 2

    @staticmethod
    def _get_system_type_string(project_data: dict) -> str:
        if OfficeDocumentManager._get_system_type(project_data) == 0:
            return r""
        elif OfficeDocumentManager._get_system_type(project_data) == 1:
            return r""
        else:
            return r"PV & ESS Systems"
    
    @staticmethod
    def _get_system_type_short(project_data: dict) -> str:
        if OfficeDocumentManager._get_system_type(project_data) == 0:
            return r"PV"
        elif OfficeDocumentManager._get_system_type(project_data) == 1:
            return r"ESS"
        else:
            return r"PV ESS"

        
    def copy_to_fileserver(self, project_id: str, project_data: dict) -> Path:
        destination_root = os.getenv("FILESERVER_BIDS_FOLDER")
        if not destination_root:
            raise ValueError("FILESERVER_BIDS_FOLDER environment variable is not set.")

        source_folder = Path("projects") / str(project_id)
        destination_folder = Path(destination_root) / f"{project_data['client_name'].split()[-1]}, {project_data['client_name'].split()[0]}"
        destination_folder.mkdir(parents=True, exist_ok=True)

        shutil.copy(Path(source_folder) / "documents" / "final_proposal.pdf", destination_folder / f"{datetime.now().strftime('%y_%m%d')} {project_data['client_name'].split()[-1]}, {project_data['client_name'].split()[0]} {self._get_system_type_short(project_data)} Proposal.pdf")
        shutil.copy(Path(source_folder) / "documents" / "pricing_spreadsheet.xlsx", destination_folder / f"{datetime.now().strftime('%y_%m%d')} {project_data['client_name'].split()[-1]}, {project_data['client_name'].split()[0]} PV ESS Bid.xlsx")
        shutil.copy(Path(source_folder) / "documents" / "cover_letter.docx", destination_folder / f"PV ESS Proposal - {project_data['client_name'].split()[-1]}, {project_data['client_name'].split()[0]}.docx")
        shutil.copy(Path(source_folder) / "documents" / "solargraf_proposal.pdf", destination_folder / f"Proposal for - {project_data['client_name']}.pdf")
        shutil.copytree(Path(source_folder) / "images", destination_folder / "images", dirs_exist_ok=True)

        return destination_folder


if __name__ == "__main__":
    import json
    import pprint

    manager = OfficeDocumentManager()
    project_data = json.load(open("projects/3375365/data.json", "r", encoding="utf-8"))
    pprint.pprint(manager._generate_mapping(project_data))
    manager.copy_to_fileserver(3375365, project_data)
