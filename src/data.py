import json
from dataclasses import dataclass
import os
from pathlib import Path
from settings import SettingsManager

class DataManager():
    def __init__(self):
        self.data = {}
        self.settings = SettingsManager()
        self.project = self.Project()
        self.client = self.Client()
        self.system = self.System()
        self.pricing = self.Pricing()
        self.files = self.Files()
        self.aliases = {
        }
    
    def load_json(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                self.data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

        self.project.id = self.data["id"]
        self.project.name = self.client.name.upper()
        
        self.client.first_name = self.data["client_name"].split()[0]
        self.client.last_name = " ".join(self.data["client_name"].split()[1:])
        self.client.name = self.data["client_name"]
        self.client.phone = self.data["client_phone"]
        self.client.email = self.data["client_email"]
        self.client.address.street = self.data["Position"]["street"]
        self.client.address.city = self.data["Position"]["city"]
        self.client.address.region_code = self.data["Position"]["region_code"]
        self.client.address.postal_code = self.data["Position"]["postal_code"]

        self.system.type = self._get_system_type()
        self.system.size = self.data["sizeInKw"]
        self.system.panel.manufacturer = self.alias(self.data["Materials"]["panel"][0]["Manufacturer"]["name"])
        self.system.panel.model = self.alias(self.data["Materials"]["panel"][0]["name"])
        self.system.panel.type = self.data["Materials"]["panel"][0]["type"]
        self.system.panel.size = self.data["Materials"]["panel"][0]["size_in_watts"]
        self.system.panel.ptc = self.data["Materials"]["panel"][0]["ptc_in_watts"]
        self.system.panel.warranty = self.data["Materials"]["panel"][0]["warranty"]
        self.system.panel.count = self.data["Materials"]["panel"][0]["count"]
        self.system.panel.specsheet_url = self.data["Materials"]["panel"][0]["spec_sheet"]
        self.system.inverter.manufacturer = self.alias(self.data["Materials"]["inverter"][0]["Manufacturer"]["name"])
        self.system.inverter.model = self.alias(self.data["Materials"]["inverter"][0]["name"])
        self.system.inverter.warranty = self.data["Materials"]["inverter"][0]["warranty"]
        self.system.inverter.count = self.data["Materials"]["inverter"][0]["count"]
        self.system.inverter.specsheet_url = self.data["Materials"]["inverter"][0]["spec_sheet"]
        self.system.battery.manufacturer = self.alias(self.data["Materials"]["batteryBackup"][0]["Manufacturer"]["name"])
        self.system.battery.model = self.alias(self.data["Materials"]["batteryBackup"][0]["name"])
        self.system.battery.capacity = self.data["Materials"]["batteryBackup"][0]["capacity"]
        self.system.battery.warranty = self.data["Materials"]["batteryBackup"][0]["warranty"]
        self.system.battery.count = self.data["Materials"]["batteryBackup"][0]["count"]
        self.system.battery.specsheet_url = self.data["Materials"]["batteryBackup"][0]["spec_sheet"]
        
        self.pricing.id = self.data["Settings"]["Pricing"]["FinancialOptions"][0]["id"]
        
        self.files.pricing_spreadsheet_template = self.settings.files.templates_folder / "pricing_spreadsheet.xlsx"
        self.files.cover_letter_template = self.settings.files.templates_folder / f"cover_letter_{self.system.type}.docx"
        self.files.solargraf_proposal_template = self.settings.files.templates_folder / "generated_proposal.docx"
        self.files.email_template = self.settings.files.templates_folder / "email.html"
        self.files.project_folder = self.settings.files.projects_folder / str(self.project.id)
        self.files.images_folder = self.files.project_folder / "images"
        self.files.documents_folder = self.files.project_folder / "documents"
        self.files.specsheets_folder = self.files.documents_folder / "specsheets"
        self.files.solargraf_proposal = self.files.documents_folder / "solargraf_proposal.pdf"
        self.files.pricing_spreadsheet = self.files.documents_folder / "pricing_spreadsheet.xlsx"
        self.files.cover_letter_docx = self.files.documents_folder / "cover_letter.docx"
        self.files.cover_letter_pdf = self.files.documents_folder / "cover_letter.pdf"
        self.files.final_proposal = self.files.documents_folder / "final_proposal.pdf"

    def set_api_id(self, api_id):
        self.project.api_id = api_id
        
    def set_annual_production(self, annual_production):
        self.system.annual_production = annual_production
        
    def alias(self, value):
        return self.aliases.get(value, value)
    
    def _get_system_type(self):
        if self.data["is_roofing_only"]:
            return 0
        elif self.data["is_battery_only"]:
            return 1
        else:
            return 2

    @dataclass
    class Project():
        id: int = 0
        api_id: str = ""
        name: str = ""
    
    class Client():
        def __init__(self):
            self.first_name: str = ""
            self.last_name: str = ""
            self.name: str = ""
            self.phone: str = ""
            self.email: str = ""
            self.address = self.Address()
        
        @dataclass
        class Address():
            street: str = ""
            city: str = ""
            region_code: str = ""
            postal_code: str = ""
    
    @dataclass
    class System():
        def __init__(self):
            self.type: int = 0
            self.size: float = 0.0
            self.panel = self.Panel()
            self.inverter = self.Inverter()
            self.battery = self.Battery()
            self.usage = []
            self.annual_production: float = 0.0

        @dataclass
        class Panel():
            manufacturer: str = ""
            model: str = ""
            size: int = 0
            type: str = ""
            warranty: int = 0
            ptc: int = 0
            count: int = 0
            specsheet_url: str = ""
            
        @dataclass
        class Inverter():
            manufacturer: str = ""
            model: str = ""
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""
        
        @dataclass
        class Battery():
            manufacturer: str = ""
            model: str = ""
            capacity: float = 0.0
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""
    
    @dataclass
    class Pricing():
        id: str = ""
        panel_cost: float = 0.0
        inverter_cost: float = 0.0
        battery_cost: float = 0.0
        total_cost: float = 0.0
        cost_per_watt: float = 0.0
        loan_term: int = 12
        loan_interest_rate: float = float(os.getenv("LOAN_INTEREST_RATE", "0.0"))
        
    @dataclass
    class Files():
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
        
