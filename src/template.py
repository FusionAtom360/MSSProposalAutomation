from data import DataManager
from openpyxl import load_workbook

class TemplateManager:
    def __init__(self, data):
        self.templates = {}
        self.update(data)

    def update(self, data: DataManager):
        print(data.project.name.upper())
        self.templates[r"{{JOB_NAME}}"] = data.project.name.upper()
        self.templates[r"{{CLIENT_NAME}}"] = data.client.name
        self.templates[r"{{CLIENT_FIRST_NAME}}"] = data.client.first_name
        self.templates[r"{{CLIENT_LAST_NAME}}"] = data.client.last_name
        self.templates[r"{{CLIENT_PHONE}}"] = data.client.phone
        self.templates[r"{{CLIENT_EMAIL}}"] = data.client.email
        self.templates[r"{{CLIENT_ADDRESS_1}}"] = data.client.address.street
        self.templates[r"{{CLIENT_ADDRESS_2}}"] = (
            f"{data.client.address.city}, {data.client.address.region_code} {data.client.address.postal_code}"
        )
        self.templates[r"{{CLIENT_ADDRESS_STREET}}"] = data.client.address.street
        self.templates[r"{{CLIENT_ADDRESS_CITY}}"] = data.client.address.city
        self.templates[r"{{CLIENT_ADDRESS_ZIP}}"] = data.client.address.postal_code

        self.templates[r"{{PANEL_MANUFACTURER}}"] = data.system.panel.manufacturer
        self.templates[r"{{PANEL_MODEL}}"] = data.system.panel.model
        self.templates[r"{{PANEL_TYPE}}"] = (
            "monocrystalline" if data.system.panel.type == "mono"
            else "polycrystalline" if data.system.panel.type == "poly"
            else "bifacial"
        )
        self.templates[r"{{PANEL_SIZE}}"] = data.system.panel.size
        self.templates[r"{{PANEL_PTC_RATIO}}"] = round(
            data.system.panel.ptc / data.system.panel.size * 100
        ) if data.system.panel.size and data.system.panel.ptc else None
        self.templates[r"{{PANEL_WARRANTY}}"] = data.system.panel.warranty
        self.templates[r"{{PANEL_COUNT}}"] = data.system.panel.count

        self.templates[r"{{INVERTER_MANUFACTURER}}"] = data.system.inverter.manufacturer
        self.templates[r"{{INVERTER_MODEL}}"] = data.system.inverter.model
        self.templates[r"{{INVERTER_WARRANTY}}"] = data.system.inverter.warranty
        self.templates[r"{{INVERTER_COUNT}}"] = data.system.inverter.count

        self.templates[r"{{BATTERY_MANUFACTURER}}"] = data.system.battery.manufacturer
        self.templates[r"{{BATTERY_MODEL}}"] = data.system.battery.model
        self.templates[r"{{BATTERY_CAPACITY}}"] = data.system.battery.capacity
        self.templates[r"{{BATTERY_WARRANTY}}"] = data.system.battery.warranty
        self.templates[r"{{BATTERY_COUNT}}"] = data.system.battery.count

        self.templates[r"{{SYSTEM_TYPE}}"] = data.system.type
        self.templates[r"{{PV_SIZE}}"] = data.system.pv_size
        self.templates[r"{{ESS_SIZE}}"] = data.system.ess_size
        self.templates[r"{{ESS_TYPE}}"] = "w/ IQ Meter Collar (for Off-Grid Backup Operation)" if data.system.ess_type == 0 else "w/o Meter Collar (for On-Grid Operation ONLY)"

        self.templates[r"{{ENPHASE_PLATINUM_INSTALLER}}"] = (
            "As an Enphase Platinum Installer, Mid-State Solar has been installing Enphase products since 2009."
            if data.system.inverter.manufacturer == "Enphase Energy Inc."
            else ""
        )
        self.templates[r"{{BATTERY_PLURAL}}"] = "Batteries" if data.system.battery.count > 1 else "Battery"
        
        # Update with values from the pricing spreadsheet if it exists
        if data.files.pricing_spreadsheet.is_file():
            workbook = load_workbook(data.files.pricing_spreadsheet, data_only=True, read_only=True)
            sheet = workbook["Edit Variables"]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                placeholder, value = row[0], row[1]
                if placeholder and value is not None:
                    if str(self.templates[str(placeholder)]) == str(value):
                        continue
                    else:
                        self.templates[str(placeholder)] = str(value)
            
        

    def get_all(self):
        return self.templates

    def resolve(self, template_name):
        return self.templates.get(template_name, template_name)

# Additional IQ10C Battery Unit: $8,340 
# Dedicated Subpanel (Critical Loads Backup) for Off-Grid use: $3,650
# IQ60 EV Charger w/ Smart Solar Interface: $1,860
