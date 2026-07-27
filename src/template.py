from data import DataManager

class TemplateManager:
    def __init__(self, data):
        self.templates = {}
        self.update(data)
    
    def update(self, data: DataManager):
        self.templates[r"{{JOB_NAME}}"] = data.project.name.upper()
        self.templates[r"{{CLIENT_NAME}}"] = data.client.name
        self.templates[r"{{CLIENT_FIRST_NAME}}"] = data.client.first_name
        self.templates[r"{{CLIENT_LAST_NAME}}"] = data.client.last_name
        self.templates[r"{{CLIENT_PHONE}}"] = data.client.phone
        self.templates[r"{{CLIENT_EMAIL}}"] = data.client.email
        self.templates[r"{{PROJECT_NAME}}"] = data.project.name
        self.templates[r"{{CUSTOMER_ADDRESS_1}}"] = data.client.address.street
        self.templates[r"{{CUSTOMER_ADDRESS_2}}"] = f"{data.client.address.city}, {data.client.address.region_code} {data.client.address.postal_code}"
        self.templates[r"{{CUSTOMER_ADDRESS_STREET}}"] = data.client.address.street
        self.templates[r"{{CUSTOMER_ADDRESS_CITY}}"] = data.client.address.city
        self.templates[r"{{CUSTOMER_ADDRESS_ZIP}}"] = data.client.address.postal_code

    def get_all(self):
        return self.templates
    
    def resolve(self, template_name):
        return self.templates.get(template_name, template_name)

# def _generate_mapping(self, project_data: dict) -> dict[str, any]:
#         mapping = {
#             r"{{JOB_NAME}}": project_data["client_name"].upper(),
#             r"{{CUSTOMER_NAME}}": project_data["client_name"],
#             r"{{CUSTOMER_FIRST_NAME}}": project_data["client_name"].split()[0],
#             r"{{CUSTOMER_LAST_NAME}}": project_data["client_name"].split()[-1],
#             r"{{CUSTOMER_ADDRESS_1}}": project_data["Position"]["street"],
#             r"{{CUSTOMER_ADDRESS_2}}": f"{project_data['Position']['city']}, {project_data['Position']['region_code']} {project_data['Position']['postal_code']}",
#             r"{{CUSTOMER_ADDRESS_STREET}}": project_data["Position"]["street"],
#             r"{{CUSTOMER_ADDRESS_CITY}}": project_data["Position"]["city"],
#             r"{{CUSTOMER_ADDRESS_ZIP}}": project_data["Position"]["postal_code"],
#             r"{{USAGE_JAN}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][0]["amount"],
#             r"{{USAGE_FEB}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][1]["amount"],
#             r"{{USAGE_MAR}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][2]["amount"],
#             r"{{USAGE_APR}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][3]["amount"],
#             r"{{USAGE_MAY}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][4]["amount"],
#             r"{{USAGE_JUN}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][5]["amount"],
#             r"{{USAGE_JUL}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][6]["amount"],
#             r"{{USAGE_AUG}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][7]["amount"],
#             r"{{USAGE_SEP}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][8]["amount"],
#             r"{{USAGE_OCT}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][9]["amount"],
#             r"{{USAGE_NOV}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][10]["amount"],
#             r"{{USAGE_DEC}}": project_data["Settings"]["Pricing"]["ProjectConnection"][
#                 "Bills"
#             ][11]["amount"],
#             r"{{PREPARED_DATE}}": datetime.now().strftime("%B %d, %Y"),
#             r"{{START_YEAR}}": str(datetime.now().year),
#             r"{{CUSTOMER_EMAIL}}": project_data["client_email"],
#             r"{{CUSTOMER_PHONE}}": project_data["client_phone"],
#             r"{{SYSTEM_TYPE}}": self._get_system_type_string(project_data),
#             r"{{PANEL_STC}}": project_data["Materials"]["panel"][0]["size_in_watts"],
#             # r"{{PANEL_PTC_RATIO}}": project_data["Materials"]["panel"][0]["ptc_in_watts"] / project_data["Materials"]["panel"][0]["size_in_watts"],
#             r"{{PANEL_MANUFACTURER}}": project_data["Materials"]["panel"][0][
#                 "Manufacturer"
#             ]["name"],
#             r"{{PANEL_MANUFACTURER_UPPERCASE}}": project_data["Materials"]["panel"][0][
#                 "Manufacturer"
#             ]["name"].upper(),
#             r"{{INVERTER_MANUFACTURER}}": project_data["Materials"]["inverter"][0][
#                 "Manufacturer"
#             ]["name"],
#             r"{{INVERTER_MANUFACTURER_UPPERCASE}}": project_data["Materials"][
#                 "inverter"
#             ][0]["Manufacturer"]["name"].upper(),
#             r"{{ENPHASE_PLATINUM_INSTALLER}}": self._get_enphase_message(project_data),
#             r"{{PV_SIZE}}": project_data["proposals"][0]["sizeInKw"],
#             r"{{PANEL_QUANTITY}}": project_data["Materials"]["panel"][0]["count"],
#             r"{{PV_PRICE}}": f"${self._get_pv_price(project_data):,}",
#             # r"{{TOTAL_PRICE}}": f"${self._get_pv_price(project_data)+self._get_storage_price(project_data):,}",
#             r"{{LOAN_PAYMENT}}": f"${self._calculate_loan_payment(project_data):,}",
#             r"{{PANEL_WARRANTY}}": project_data["Materials"]["panel"][0]["warranty"],
#             # r"{{INVERTER_WARRANTY}}": project_data["Materials"]["inverter"][0]["warranty"],
#             r"{{BATTERY_SIZE}}": project_data["StorageSettings"][0]["minStorageReq"],
#             r"{{BATTERY_COUNT}}": project_data["Materials"]["batteryBackup"][0][
#                 "count"
#             ],
#             r"{{BATTERY_MODEL}}": project_data["Materials"]["batteryBackup"][0]["name"],
#             r"{{BATTERY_WARRANTY}}": project_data["Materials"]["batteryBackup"][0][
#                 "warranty"
#             ],
#             # r"{{BATTERY_WARRANTY_CYCLES}}": 6000,
#             # r"{{STORAGE_PRICE}}":  f"${self._get_storage_price(project_data):,}",
#             r"{{LOAN_TERM}}": os.getenv("LOAN_TERM"),
#             r"{{LOAN_INTEREST_RATE}}": float(os.getenv("LOAN_INTEREST_RATE")) * 100,
#             r"{{TOTAL_USAGE}}": self._get_total_usage(project_data),
#             # r"{{TOTAL_SIZE}}": "
#             #r"{{USAGE_PERCENTAGE}}": int(project_data["proposals"][0]["sizeInKw"] / (self._get_total_usage(project_data) / 1000) * 100),
#         }
#         for key, value in mapping.items():
#             if value in self.alias_mapping:
#                 mapping[key] = self.alias_mapping[value]
#         return mapping

    # @staticmethod
    # def _get_enphase_message(project_data: dict) -> str:
    #     if (
    #         project_data["Materials"]["inverter"][0]["Manufacturer"]["name"].lower()
    #         == "enphase"
    #     ):
    #         return "As an Enphase Platinum Installer, Mid-State Solar has been installing Enphase products since 2009."
    #     else:
    #         return ""
