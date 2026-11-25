"""Resolve proposal placeholders from project data and workbook settings."""

import datetime

from data import DataManager
from field_schema import FieldProvenance, ValidationIssue, ValidationReport
from openpyxl import load_workbook
from datetime import datetime

class TemplateManager:
    """Build and resolve document placeholders with provenance information."""

    def __init__(self, data: DataManager):
        """Initialize placeholder state and populate it from project data."""
        self.templates = {}
        self.aliases = {}
        self.provenance = {}
        self.unresolved_placeholders = set()
        self.validation_report = ValidationReport()
        self.update(data)

    def update(self, data: DataManager):
        """Refresh placeholders, aliases, provenance, and validation warnings."""
        self.unresolved_placeholders = set()
        self.validation_report = ValidationReport(
            enforcement=data.field_schema.enforcement
        )
        for placeholder in (
            "{{PV_SIZE}}",
            "{{TOTAL_SIZE}}",
            "{{USAGE_PERCENTAGE}}",
        ):
            provenance = self.provenance.get(placeholder)
            if provenance is not None and provenance.source == "solargraf_pdf":
                self.provenance.pop(placeholder, None)
                if placeholder != "{{PV_SIZE}}":
                    self.templates.pop(placeholder, None)
        self._update_from_settings_spreadsheet(data)
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

        self.templates[r"{{UTILITY_NAME}}"] = self.aliases.get(data.utility.name, data.utility.name)
        self.templates[r"{{ANNUAL_CONSUMPTION}}"] = data.utility.annual_consumption

        self.templates[r"{{PANEL_MANUFACTURER}}"] = self.aliases.get(data.system.panel.manufacturer, data.system.panel.manufacturer)
        self.templates[r"{{PANEL_MANUFACTURER_UPPERCASE}}"] = self.aliases.get(data.system.panel.manufacturer, data.system.panel.manufacturer).upper() if data.system.panel.manufacturer else None
        self.templates[r"{{PANEL_MODEL}}"] = self.aliases.get(data.system.panel.model, data.system.panel.model)
        self.templates[r"{{PANEL_TYPE}}"] = (
            "monocrystalline" if data.system.panel.type == "mono"
            else "polycrystalline" if data.system.panel.type == "poly"
            else "bifacial"
        )
        self.templates[r"{{PANEL_SIZE}}"] = data.system.panel.size
        self.templates[r"{{PANEL_PTC}}"] = data.system.panel.ptc
        self.templates[r"{{PANEL_PTC_RATIO}}"] = round(
            data.system.panel.ptc / data.system.panel.size * 100
        ) if data.system.panel.size and data.system.panel.ptc else None
        self.templates[r"{{PANEL_WARRANTY}}"] = data.system.panel.warranty
        self.templates[r"{{PANEL_COUNT}}"] = data.system.panel.count

        self.templates[r"{{INVERTER_MANUFACTURER}}"] = self.aliases.get(data.system.inverter.manufacturer, data.system.inverter.manufacturer)
        self.templates[r"{{INVERTER_MANUFACTURER_UPPERCASE}}"] = self.aliases.get(data.system.inverter.manufacturer, data.system.inverter.manufacturer).upper() if data.system.inverter.manufacturer else None
        self.templates[r"{{INVERTER_MODEL}}"] = self.aliases.get(data.system.inverter.model, data.system.inverter.model)
        self.templates[r"{{INVERTER_WARRANTY}}"] = data.system.inverter.warranty
        self.templates[r"{{INVERTER_COUNT}}"] = data.system.inverter.count
        self.templates[r"{{INVERTER_EFFICIENCY}}"] = f"{round(data.system.inverter.efficiency*100)}" if data.system.inverter.efficiency else None

        if data.system.type != 0:
            self.templates[r"{{BATTERY_MANUFACTURER}}"] = self.aliases.get(data.system.battery.manufacturer, data.system.battery.manufacturer)
            self.templates[r"{{BATTERY_MANUFACTURER_UPPERCASE}}"] = self.aliases.get(data.system.battery.manufacturer, data.system.battery.manufacturer).upper() if data.system.battery.manufacturer else None
            self.templates[r"{{BATTERY_MODEL}}"] = self.aliases.get(data.system.battery.model, data.system.battery.model)
            self.templates[r"{{BATTERY_CAPACITY}}"] = data.system.battery.capacity
            self.templates[r"{{BATTERY_WARRANTY}}"] = data.system.battery.warranty
            self.templates[r"{{BATTERY_WARRANTY_CYCLES}}"] = data.system.battery.warranty * 400 if data.system.battery.warranty else None
            self.templates[r"{{BATTERY_WARRANTY_CAPACITY}}"] = 60
            self.templates[r"{{BATTERY_COUNT}}"] = data.system.battery.count

        self.templates[r"{{SYSTEM_TYPE}}"] = "PV" if data.system.type == 0 else "ESS" if data.system.type == 1 else "PV & ESS"
        self.templates[r"{{PV_SIZE}}"] = data.system.pv_size
        self.templates[r"{{ESS_SIZE}}"] = data.system.ess_size
        self.templates[r"{{ESS_TYPE}}"] = self.resolve(r"{{ESS_TYPE_ON_GRID}}") if data.system.ess_type == 0 else self.resolve(r"{{ESS_TYPE_OFF_GRID}}")
        self.templates[r"{{OFF_GRID_SUBPANEL}}"] = self.resolve(r"{{OFF_GRID_SUBPANEL_OPTION}}") if data.system.ess_type == 0 else self.resolve(r"{{OFF_GRID_SUBPANEL_OMIT}}")

        self.templates[r"{{PREPARED_DATE_MMDDYYYY}}"] = datetime.now().strftime("%m/%d/%Y")
        self.templates[r"{{ENPHASE_PLATINUM_INSTALLER}}"] = (
            self.resolve(r"{{ENPHASE_PLATINUM_INSTALLER}}")
            if data.system.inverter.manufacturer == "Enphase Energy Inc."
            else ""
        )
        self.templates[r"{{TREE_TRIMMING_REQUIRED}}"] = self.resolve(r"{{TREE_TRIMMING_REQUIRED}}") if data.system.tree_trimming_required else ""
        self.templates[r"{{UTILITY_NEM}}"] = self.resolve(r"{{UTILITY_NEM_MID}}") if data.utility.name == "Modesto Irrigation District" else self.resolve(r"{{UTILITY_NEM_PGE}}")
        self.templates[r"{{UTILITY_APPLICATION_DESCRIPTION}}"] = self.resolve(r"{{UTILITY_APPLICATION_DESCRIPTION_MID}}") if data.utility.name == "Modesto Irrigation District" else self.resolve(r"{{UTILITY_APPLICATION_DESCRIPTION_PGE}}")
        if data.system.type != 0:
            self.templates[r"{{BATTERY_PLURAL}}"] = "Batteries" if data.system.battery.count > 1 else "Battery"
        self.templates[r"{{UTILITY_LINK}}"] = self.resolve(r"{{UTILITY_LINK_MID}}") if data.utility.name == "Modesto Irrigation District" else self.resolve(r"{{UTILITY_LINK_PGE}}")
        self.templates[r"{{APPLICATION_FEE}}"] = self.resolve(r'{{APPLICATION_FEE_MID}}') if data.utility.name == "Modesto Irrigation District" else self.resolve(r'{{APPLICATION_FEE_PGE}}')
        self.templates[r"{{VARIANCE_APPROVAL}}"] = self.resolve(r'{{VARIANCE_APPROVAL_MID}}') if data.utility.name == "Modesto Irrigation District" else ""

        self.templates[r"{{PV_COST}}"] = f"${int(data.pricing.pv_cost):,}"
        self.templates[r"{{ESS_COST}}"] = f"${int(data.pricing.ess_cost):,}"
        self.templates[r"{{TOTAL_COST}}"] = f"${int(data.pricing.total_cost):,}"
        self.templates[r"{{LOAN_TERM}}"] = data.pricing.loan_term
        self.templates[r"{{LOAN_INTEREST_RATE}}"] = f"{data.pricing.loan_interest_rate*100:.2f}"
        self.templates[r"{{LOAN_MONTHLY_PAYMENT}}"] = f"${int(data.pricing.loan_monthly_payment):,}"

        data_fields = {
            "{{JOB_NAME}}": "project.name",
            "{{CLIENT_NAME}}": "client.name",
            "{{CLIENT_FIRST_NAME}}": "client.first_name",
            "{{CLIENT_LAST_NAME}}": "client.last_name",
            "{{CLIENT_PHONE}}": "client.phone",
            "{{CLIENT_EMAIL}}": "client.email",
            "{{CLIENT_ADDRESS_1}}": "client.address.street",
            "{{CLIENT_ADDRESS_2}}": "client.address.city",
            "{{UTILITY_NAME}}": "utility.name",
            "{{ANNUAL_CONSUMPTION}}": "utility.annual_consumption",
            "{{PANEL_MANUFACTURER}}": "system.panel.manufacturer",
            "{{PANEL_MODEL}}": "system.panel.model",
            "{{PANEL_TYPE}}": "system.panel.type",
            "{{PANEL_SIZE}}": "system.panel.size",
            "{{PANEL_PTC}}": "system.panel.ptc",
            "{{PANEL_WARRANTY}}": "system.panel.warranty",
            "{{PANEL_COUNT}}": "system.panel.count",
            "{{INVERTER_MANUFACTURER}}": "system.inverter.manufacturer",
            "{{INVERTER_MODEL}}": "system.inverter.model",
            "{{INVERTER_WARRANTY}}": "system.inverter.warranty",
            "{{INVERTER_COUNT}}": "system.inverter.count",
            "{{BATTERY_MANUFACTURER}}": "system.battery.manufacturer",
            "{{BATTERY_MODEL}}": "system.battery.model",
            "{{BATTERY_CAPACITY}}": "system.battery.capacity",
            "{{BATTERY_WARRANTY}}": "system.battery.warranty",
            "{{BATTERY_COUNT}}": "system.battery.count",
            "{{SYSTEM_TYPE}}": "system.type",
            "{{PV_SIZE}}": "system.pv_size",
            "{{ESS_SIZE}}": "system.ess_size",
            "{{PV_COST}}": "pricing.pv_cost",
            "{{ESS_COST}}": "pricing.ess_cost",
            "{{TOTAL_COST}}": "pricing.total_cost",
            "{{LOAN_TERM}}": "pricing.loan_term",
            "{{LOAN_INTEREST_RATE}}": "pricing.loan_interest_rate",
            "{{LOAN_MONTHLY_PAYMENT}}": "pricing.loan_monthly_payment",
        }
        for placeholder, field_name in data_fields.items():
            field_provenance = data.field_provenance.get(field_name)
            if field_provenance is not None:
                self.provenance[placeholder] = field_provenance

        alias_fields = [
            ("utility.name", data.utility.name),
            ("system.panel.manufacturer", data.system.panel.manufacturer),
            ("system.panel.model", data.system.panel.model),
            ("system.inverter.manufacturer", data.system.inverter.manufacturer),
            ("system.inverter.model", data.system.inverter.model),
        ]
        if data.system.type != 0:
            alias_fields.extend(
                (
                    ("system.battery.manufacturer", data.system.battery.manufacturer),
                    ("system.battery.model", data.system.battery.model),
                )
            )

        for source_field, alias in alias_fields:
            alias_provenance = self.provenance.get(f"alias:{alias}")
            if alias_provenance is not None:
                for placeholder, field_name in data_fields.items():
                    if field_name == source_field:
                        self.provenance[placeholder] = FieldProvenance(
                            source="template",
                            source_path=alias_provenance.source_path,
                            transformation="settings alias applied",
                            derived_from=(source_field,),
                        )

        if data.proposal_pdf_metrics is not None:
            metrics = data.proposal_pdf_metrics
            pdf_provenance = FieldProvenance(
                source="solargraf_pdf",
                source_path=(str(data.files.solargraf_proposal),),
                transformation="extracted from proposal PDF",
            )
            self.templates["{{PV_SIZE}}"] = metrics.system_size_kw
            self.templates["{{TOTAL_SIZE}}"] = f"{int(metrics.annual_production_kwh):,}"
            self.templates["{{USAGE_PERCENTAGE}}"] = metrics.usage_percentage
            for placeholder in (
                "{{PV_SIZE}}",
                "{{TOTAL_SIZE}}",
                "{{USAGE_PERCENTAGE}}",
            ):
                self.provenance[placeholder] = pdf_provenance
    
    def _update_from_settings_spreadsheet(self, data: DataManager):
        """Load configured aliases and fixed variables from the settings workbook."""
        if data.files.settings.is_file():
            workbook = load_workbook(data.files.settings, data_only=True, read_only=True)
            sheet = workbook["Aliases"]
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                placeholder, value = row[0], row[1]
                if placeholder and value is not None:
                    self.aliases[str(placeholder)] = str(value)
                    self.provenance[f"alias:{placeholder}"] = FieldProvenance(
                        source="template",
                        source_path=(
                            str(data.files.settings),
                            "Aliases",
                            row_number,
                            "B",
                        ),
                        transformation="settings alias",
                    )
    
            sheet = workbook["Variables"]
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                placeholder, value = row[0], row[1]
                if placeholder and value is not None:
                    self.templates[str(placeholder)] = str(value)
                    self.provenance[str(placeholder)] = FieldProvenance(
                        source="template",
                        source_path=(
                            str(data.files.settings),
                            "Variables",
                            row_number,
                            "B",
                        ),
                        transformation="settings variable",
                    )
            workbook.close()
    

    def get_all(self):
        """Return the mapping of all current placeholder values."""
        return self.templates

    def resolve(self, template_name):
        """Return a placeholder's value, recording a warning if it is missing."""
        value = self.templates.get(template_name, None)
        if value is None:
            if template_name not in self.unresolved_placeholders:
                self.unresolved_placeholders.add(template_name)
                self.validation_report.warnings.append(
                    ValidationIssue(
                        severity="warning",
                        field=template_name,
                        code="unresolved_placeholder",
                        message="Template value is not configured",
                    )
                )
            return template_name
        if template_name in self.unresolved_placeholders:
            self.unresolved_placeholders.remove(template_name)
            self.validation_report.warnings = [
                issue
                for issue in self.validation_report.warnings
                if issue.field != template_name
            ]
        return value
