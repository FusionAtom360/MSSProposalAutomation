import sys
from pathlib import Path
from typing import cast

from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import DataManager, ProposalPdfMetrics
from template import TemplateManager


def test_proposal_pdf_metrics_populate_and_clear_template_values(tmp_path):
    data = DataManager()
    data.files.settings = tmp_path / "missing-settings.xlsx"
    data.files.solargraf_proposal = tmp_path / "solargraf_proposal.pdf"
    data.system.pv_size = 7.83
    data.proposal_pdf_metrics = ProposalPdfMetrics(
        system_size_kw=11.31,
        annual_production_kwh=15925.6,
        usage_percentage=116,
    )

    templates = TemplateManager(data)

    assert templates.resolve("{{PV_SIZE}}") == 11.31
    assert templates.resolve("{{TOTAL_SIZE}}") == "15,925.6"
    assert templates.resolve("{{USAGE_PERCENTAGE}}") == 116
    assert templates.provenance["{{TOTAL_SIZE}}"].source == "solargraf_pdf"

    data.proposal_pdf_metrics = None
    templates.update(data)

    assert templates.resolve("{{PV_SIZE}}") == 7.83
    assert templates.resolve("{{TOTAL_SIZE}}") == "{{TOTAL_SIZE}}"
    assert templates.resolve("{{USAGE_PERCENTAGE}}") == "{{USAGE_PERCENTAGE}}"


def test_pv_templates_do_not_access_battery_fields():
    data = DataManager()
    data.system.type = 0
    data.project.name = "Ada Lovelace"
    data.client.name = "Ada Lovelace"
    data.utility.name = "Example Utility"
    data.system.panel.type = "mono"
    data.system.inverter.manufacturer = "Acme Inverters"
    data.pricing.loan_interest_rate = 0

    class BatteryAccessGuard:
        def __getattribute__(self, name):
            raise AssertionError(f"PV template accessed battery field: {name}")

    data.system.battery = cast(DataManager.System.Battery, BatteryAccessGuard())

    templates = TemplateManager(data)

    assert "{{BATTERY_MANUFACTURER}}" not in templates.get_all()
    assert "{{BATTERY_PLURAL}}" not in templates.get_all()


def test_unresolved_placeholders_are_reported_without_changing_resolution(tmp_path):
    data = DataManager()
    data.files.settings = tmp_path / "missing-settings.xlsx"
    templates = TemplateManager(data)

    assert templates.resolve("{{CUSTOM_UNCONFIGURED_FIELD}}") == (
        "{{CUSTOM_UNCONFIGURED_FIELD}}"
    )
    assert any(
        issue.code == "unresolved_placeholder"
        and issue.field == "{{CUSTOM_UNCONFIGURED_FIELD}}"
        for issue in templates.validation_report.warnings
    )


def test_settings_aliases_and_derived_values_are_applied(tmp_path):
    settings_path = tmp_path / "settings.xlsx"
    workbook = Workbook()
    aliases = workbook.active
    aliases.title = "Aliases"
    aliases.append(["placeholder", "replacement"])
    aliases.append(["Example Utility", "Example Power"])
    variables = workbook.create_sheet("Variables")
    variables.append(["placeholder", "value"])
    variables.append(["{{UTILITY_NEM_PGE}}", "PGE NEM terms"])
    variables.append(["{{UTILITY_APPLICATION_DESCRIPTION_PGE}}", "PGE application"])
    variables.append(["{{UTILITY_LINK_PGE}}", "https://example.com"])
    variables.append(["{{APPLICATION_FEE_PGE}}", "$0"])
    workbook.create_sheet("Spec Sheets")
    workbook.create_sheet("Spreadsheet")
    workbook.save(settings_path)

    data = DataManager()
    data.files.settings = settings_path
    data.project.name = "Ada Lovelace"
    data.client.name = "Ada Lovelace"
    data.client.first_name = "Ada"
    data.client.last_name = "Lovelace"
    data.utility.name = "Example Utility"
    data.utility.annual_consumption = 1050.5
    data.system.type = 0
    data.system.pv_size = 8.4
    data.system.panel.manufacturer = "Acme Solar"
    data.system.panel.model = "Acme 400"
    data.system.panel.type = "mono"
    data.system.panel.size = 400
    data.system.panel.ptc = 380
    data.system.panel.count = 21
    data.system.inverter.manufacturer = "Acme Inverters"
    data.system.inverter.model = "Acme 8K"
    data.system.inverter.count = 1
    data.pricing.pv_cost = 24000
    data.pricing.total_cost = 24000
    data.pricing.loan_interest_rate = 0.05
    data.pricing.loan_monthly_payment = 500

    templates = TemplateManager(data)

    assert templates.resolve("{{UTILITY_NAME}}") == "Example Power"
    assert templates.resolve("{{UTILITY_NEM}}") == "PGE NEM terms"
    assert templates.resolve("{{PANEL_PTC_RATIO}}") == 95
    assert templates.resolve("{{LOAN_INTEREST_RATE}}") == "5.00"
    assert templates.resolve("{{TOTAL_COST}}") == "$24,000"
    assert templates.provenance["{{UTILITY_NEM_PGE}}"].source == "template"
    assert templates.provenance["{{UTILITY_NEM_PGE}}"].source_path == (
        str(settings_path),
        "Variables",
        2,
        "B",
    )
    assert templates.provenance["{{UTILITY_NAME}}"].transformation == (
        "settings alias applied"
    )
