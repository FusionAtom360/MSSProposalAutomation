import json
from dataclasses import dataclass
import os
from pathlib import Path

class DataManager():
    def __init__(self):
        self.data = {}
        self.project = self.Project()
        self.client = self.Client()
        self.system = self.System()
        self.pricing = self.Pricing()
        self.aliases = {
        }
    
    def load_json(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                self.data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}

        self.project.id = self.alias(self.data["id"])
        self.client.first_name = self.alias(self.data["client_name"].split()[0])
        self.client.last_name = self.alias(" ".join(self.data["client_name"].split()[1:]))
        self.client.name = self.alias(self.data["client_name"])
        self.client.phone = self.alias(self.data["client_phone"])
        self.client.email = self.alias(self.data["client_email"])
        self.project.name = self.alias(self.client.name.upper())
        self.system.type = self.alias(self._get_system_type())
        self.system.size = self.alias(self.data["sizeInKw"])
        self.system.panel.manufacturer = self.alias(self.data["Materials"]["panel"][0]["Manufacturer"]["name"])
        self.system.panel.model = self.alias(self.data["Materials"]["panel"][0]["name"])
        self.system.panel.type = self.alias(self.data["Materials"]["panel"][0]["type"])
        self.system.panel.size = self.alias(self.data["Materials"]["panel"][0]["size_in_watts"])
        self.system.panel.ptc = self.alias(self.data["Materials"]["panel"][0]["ptc_in_watts"])
        self.system.panel.warranty = self.alias(self.data["Materials"]["panel"][0]["warranty"])
        self.system.panel.count = self.alias(self.data["Materials"]["panel"][0]["count"])
        self.system.inverter.manufacturer = self.alias(self.data["Materials"]["inverter"][0]["Manufacturer"]["name"])
        self.system.inverter.model = self.alias(self.data["Materials"]["inverter"][0]["name"])
        self.system.inverter.warranty = self.alias(self.data["Materials"]["inverter"][0]["warranty"])
        self.system.inverter.count = self.alias(self.data["Materials"]["inverter"][0]["count"])
        self.system.battery.manufacturer = self.alias(self.data["Materials"]["batteryBackup"][0]["Manufacturer"]["name"])
        self.system.battery.model = self.alias(self.data["Materials"]["batteryBackup"][0]["name"])
        self.system.battery.capacity = self.alias(self.data["Materials"]["batteryBackup"][0]["capacity"])
        self.system.battery.warranty = self.alias(self.data["Materials"]["batteryBackup"][0]["warranty"])
        self.system.battery.count = self.alias(self.data["Materials"]["batteryBackup"][0]["count"])

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
    
    @dataclass
    class Client():
        first_name: str = ""
        last_name: str = ""
        name: str = ""
        phone: str = ""
        email: str = ""
    
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
            
        @dataclass
        class Inverter():
            manufacturer: str = ""
            model: str = ""
            warranty: int = 0
            count: int = 0
        
        @dataclass
        class Battery():
            manufacturer: str = ""
            model: str = ""
            capacity: float = 0.0
            warranty: int = 0
            count: int = 0
    
    @dataclass
    class Pricing():
        panel_cost: float = 0.0
        inverter_cost: float = 0.0
        battery_cost: float = 0.0
        total_cost: float = 0.0
        cost_per_watt: float = 0.0
        loan_term: int = 12
        loan_interest_rate: float = float(os.getenv("LOAN_INTEREST_RATE", "0.0"))
        
    @dataclass
    class Files():
        solargraf_proposal: Path = Path()
        pricing_spreadsheet: Path = Path()
        cover_letter: Path = Path()
        
