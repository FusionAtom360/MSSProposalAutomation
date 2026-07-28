import json
from dataclasses import dataclass
import os
from pathlib import Path
from settings import SettingsManager
from datetime import datetime


class DataManager:
    def __init__(self):
        self.data = {}
        self.settings = SettingsManager()
        self.project = self.Project()
        self.client = self.Client()
        self.system = self.System()
        self.pricing = self.Pricing()
        self.files = self.Files()

    def load_json(self, json_data: dict):
        self.data = json_data
        self.project.id = self.data["id"]

        self.client.first_name = self.data["client_name"].split()[0]
        self.client.last_name = " ".join(self.data["client_name"].split()[1:])
        self.client.name = self.data["client_name"]
        self.client.phone = self.data["client_phone"]
        self.client.email = self.data["client_email"]
        self.client.address.street = self.data["Position"]["street"]
        self.client.address.city = self.data["Position"]["city"]
        self.client.address.region_code = self.data["Position"]["region_code"]
        self.client.address.postal_code = self.data["Position"]["postal_code"]

        self.project.name = self.client.name.upper()

        self.system.type = self._get_system_type()
        self.system.pv_size = self.data["proposals"][0]["sizeInKw"]
        self.system.panel.manufacturer = self.data["Materials"]["panel"][0][
            "Manufacturer"
        ]["name"]
        self.system.panel.model = self.data["Materials"]["panel"][0]["name"]
        self.system.panel.type = self.data["Materials"]["panel"][0]["type"]
        self.system.panel.size = self.data["Materials"]["panel"][0]["size_in_watts"]
        self.system.panel.ptc = self.data["Materials"]["panel"][0]["ptc_in_watts"]
        self.system.panel.warranty = self.data["Materials"]["panel"][0]["warranty"]
        self.system.panel.count = self.data["Materials"]["panel"][0]["count"]
        self.system.panel.specsheet_url = self.data["Materials"]["panel"][0][
            "spec_sheet"
        ]

        self.system.inverter.manufacturer = self.data["Materials"]["inverter"][0][
            "Manufacturer"
        ]["name"]
        self.system.inverter.model = self.data["Materials"]["inverter"][0]["name"]
        self.system.inverter.warranty = self.data["Materials"]["inverter"][0][
            "warranty"
        ]
        self.system.inverter.count = self.data["Materials"]["inverter"][0]["count"]
        self.system.inverter.specsheet_url = self.data["Materials"]["inverter"][0][
            "spec_sheet"
        ]

        self.system.battery.manufacturer = self.data["Materials"]["batteryBackup"][0][
            "Manufacturer"
        ]["name"]
        self.system.battery.model = self.data["Materials"]["batteryBackup"][0]["name"]
        self.system.battery.capacity = self.data["Materials"]["batteryBackup"][0][
            "capacity"
        ]
        self.system.battery.warranty = self.data["Materials"]["batteryBackup"][0][
            "warranty"
        ]
        self.system.battery.count = self.data["Materials"]["batteryBackup"][0]["count"]
        self.system.battery.specsheet_url = self.data["Materials"]["batteryBackup"][0][
            "spec_sheet"
        ]
        self.system.ess_size = self.system.battery.capacity * self.system.battery.count

        self.project.financial_id = self.data["Settings"]["Pricing"][
            "FinancialOptions"
        ][0]["id"]
        self.project.proposal_id = self.data["Settings"]["Pricing"][
            "ProjectConnection"
        ]["proposal_id"]

        self.files.pricing_spreadsheet_template = (
            self.settings.files.templates_folder / "pricing_spreadsheet.xlsx"
        )
        self.files.cover_letter_template = (
            self.settings.files.templates_folder
            / f"cover_letter_{self.system.type}.docx"
        )
        self.files.solargraf_proposal_template = (
            self.settings.files.templates_folder / "generated_proposal.docx"
        )
        self.files.email_template = self.settings.files.templates_folder / "email.html"
        self.files.project_folder = self.settings.files.projects_folder / str(
            self.project.id
        )
        self.files.images_folder = self.files.project_folder / "images"
        self.files.documents_folder = self.files.project_folder / "documents"
        self.files.specsheets_folder = self.files.documents_folder / "specsheets"
        self.files.solargraf_proposal = (
            self.files.documents_folder / "solargraf_proposal.pdf"
        )
        self.files.pricing_spreadsheet = (
            self.files.documents_folder / "pricing_spreadsheet.xlsx"
        )
        self.files.cover_letter_docx = self.files.documents_folder / "cover_letter.docx"
        self.files.cover_letter_pdf = self.files.documents_folder / "cover_letter.pdf"
        self.files.final_proposal = (
            self.files.documents_folder
            / f"{datetime.now().strftime('%y_%m%d')} {self.client.last_name}, {self.client.first_name} {"PV" if self.system.type == 0 else "ESS" if self.system.type == 1 else "PV ESS"} Proposal.pdf"
        )

        self.files.project_folder.mkdir(parents=True, exist_ok=True)
        self.files.images_folder.mkdir(parents=True, exist_ok=True)
        self.files.documents_folder.mkdir(parents=True, exist_ok=True)
        self.files.specsheets_folder.mkdir(parents=True, exist_ok=True)
        with open(self.files.project_folder / "data.json", "w") as f:
            json.dump(self.data, f, indent=4)

    def set_api_id(self, api_id):
        self.project.api_id = api_id

    def _set_annual_production(self, annual_production):
        self.system.annual_production = annual_production

    def update_from_pricing_spreadsheet(self, get_cell_value_func):
        self.pricing.pv_cost = get_cell_value_func(self, "Pricing Calculator", "D88")
        self.pricing.ess_cost = get_cell_value_func(
            self, "Pricing Calculator", "D89"
        )
        self.pricing.total_cost = get_cell_value_func(self, "Pricing Calculator", "D90")
        self.pricing.loan_term = get_cell_value_func(self, "Pricing Calculator", "D91")
        self.pricing.loan_interest_rate = get_cell_value_func(
            self, "Pricing Calculator", "D92"
        )
        self.pricing.loan_monthly_payment = get_cell_value_func(
            self, "Pricing Calculator", "D93"
        )

    def _get_system_type(self):
        if self.data["is_roofing_only"]:
            return 0
        elif self.data["is_battery_only"]:
            return 1
        else:
            return 2

    def _get_ess_type(self):
        if self.data["StorageSettings"][0]["isGridTiedBattery"]:
            return 1
        return 0

    @dataclass
    class Project:
        id: int = 0
        api_id: str = ""
        financial_id: str = ""
        proposal_id: str = ""
        name: str = ""

    class Client:
        def __init__(self):
            self.first_name: str = ""
            self.last_name: str = ""
            self.name: str = ""
            self.phone: str = ""
            self.email: str = ""
            self.address = self.Address()

        @dataclass
        class Address:
            street: str = ""
            city: str = ""
            region_code: str = ""
            postal_code: str = ""

    @dataclass
    class System:
        def __init__(self):
            self.type: int = 0
            self.ess_type: int = 0
            self.pv_size: float = 0.0
            self.ess_size: float = 0.0
            self.panel = self.Panel()
            self.inverter = self.Inverter()
            self.battery = self.Battery()
            self.usage = []
            self.annual_production: float = 0.0

        @dataclass
        class Panel:
            manufacturer: str = ""
            model: str = ""
            size: int = 0
            type: str = ""
            warranty: int = 0
            ptc: int = 0
            count: int = 0
            specsheet_url: str = ""

        @dataclass
        class Inverter:
            manufacturer: str = ""
            model: str = ""
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""

        @dataclass
        class Battery:
            manufacturer: str = ""
            model: str = ""
            capacity: float = 0.0
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""

    @dataclass
    class Pricing:
        id: str = ""
        pv_cost = 0.0
        ess_cost: float = 0.0
        total_cost: float = 0.0
        cost_per_watt: float = 0.0
        loan_term: int = int(os.getenv("LOAN_TERM", "0"))
        loan_interest_rate: float = float(os.getenv("LOAN_INTEREST_RATE", "0.0"))
        loan_monthly_payment: int = 0

    @dataclass
    class Files:
        pricing_spreadsheet_template: Path = Path()
        cover_letter_template: Path = Path()
        solargraf_proposal_template: Path = Path()
        email_template: Path = Path()
        project_folder: Path = Path()
        images_folder: Path = Path()
        documents_folder: Path = Path()
        specsheets_folder: Path = Path()
        solargraf_proposal: Path = Path()
        pricing_spreadsheet: Path = Path()
        cover_letter_docx: Path = Path()
        cover_letter_pdf: Path = Path()
        final_proposal: Path = Path()
