import json
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import DataManager


def test_missing_battery_data_classifies_system_as_pv():
    data = DataManager()

    data.load_json(
        {
            "id": 123,
            "public_id": "project-api-id",
            "client_name": "Ada Lovelace",
            "Materials": {},
        },
        save_to_file=False,
    )

    assert data.system.type == 0


def test_battery_and_roofing_flags_classify_system_types():
    materials = {
        "batteryBackup": [
            {
                "Manufacturer": {"name": "Acme Storage"},
                "name": "Acme Battery",
            }
        ]
    }

    roofing_only = DataManager()
    roofing_only.load_json(
        {
            "client_name": "Ada Lovelace",
            "Materials": materials,
            "is_roofing_only": True,
        },
        save_to_file=False,
    )
    assert roofing_only.system.type == 0

    battery_only = DataManager()
    battery_only.load_json(
        {
            "client_name": "Ada Lovelace",
            "Materials": materials,
            "is_battery_only": True,
        },
        save_to_file=False,
    )
    assert battery_only.system.type == 1

    combined = DataManager()
    combined.load_json(
        {
            "client_name": "Ada Lovelace",
            "Materials": materials,
        },
        save_to_file=False,
    )
    assert combined.system.type == 2


def test_load_json_normalizes_project_customer_system_and_consumption():
    data = DataManager()
    payload = {
        "id": 123,
        "public_id": "project-api-id",
        "client_name": "Ada Lovelace",
        "client_phone": "555-0100",
        "Position": {
            "street": "1 Analytical Engine Way",
            "city": "London",
            "region_code": "CA",
            "postal_code": "90210",
        },
        "is_roofing_only": True,
        "proposals": [{"sizeInKw": 8.4}],
        "Materials": {
            "panel": [
                {
                    "Manufacturer": {"name": "Acme Solar"},
                    "name": "Acme 400",
                    "type": "mono",
                    "size_in_watts": 400,
                    "warranty": 25,
                    "ptc": 380,
                    "count": 21,
                    "spec_sheet": "https://example.com/panel.pdf",
                }
            ],
            "inverter": [
                {
                    "Manufacturer": {"name": "Acme Inverters"},
                    "name": "Acme 8K",
                    "warranty": 12,
                    "count": 1,
                    "spec_sheet": "https://example.com/inverter.pdf",
                }
            ],
        },
        "Settings": {
            "Pricing": {
                "ProjectConnection": {
                    "genability_lse_name": "Example Utility",
                    "proposal_id": "proposal-id",
                    "Bills": [
                        {"consumptionInKwh": 400},
                        {"consumptionInKwh": 650.5},
                    ],
                },
                "FinancialOptions": [{"id": "financial-id"}],
            }
        },
    }

    data.load_json(payload, save_to_file=False)

    assert data.project.id == 123
    assert data.client.first_name == "Ada"
    assert data.client.last_name == "Lovelace"
    assert data.system.type == 0
    assert data.system.pv_size == 8.4
    assert data.system.panel.size == 400
    assert data.utility.annual_consumption == 1050.5
    assert data.project.financial_id == "financial-id"
    assert data.project.proposal_id == "proposal-id"
    assert data.is_validated
    assert data.validation_report.to_dict()["is_valid"]
    assert data.field_provenance["client.name"].source == "solargraf"
    assert data.field_provenance["client.email"].source == "fallback"
    assert data.field_provenance["system.type"].source == "derived"


def test_json_schema_controls_mapping_and_advisory_or_enforced_validation(tmp_path):
    schema_path = tmp_path / "field_schema.json"
    data = DataManager()
    data.field_schema_path = schema_path
    schema = {
        "version": 1,
        "enforcement": "advisory",
        "source_paths": {"project.id": ["SolarProjectId"]},
        "defaults": {"client.email": "not-configured@example.invalid"},
        "validation": {
            "blocking_schema": {
                "type": "object",
                "properties": {
                    "project": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "minimum": 1}
                        },
                    },
                    "system": {
                        "type": "object",
                        "if": {
                            "properties": {"type": {"const": 1}},
                            "required": ["type"],
                        },
                        "then": {
                            "properties": {
                                "battery": {
                                    "type": "object",
                                    "required": ["manufacturer"],
                                    "properties": {
                                        "manufacturer": {
                                            "type": "string",
                                            "minLength": 1,
                                        }
                                    },
                                }
                            }
                        },
                    },
                },
            },
            "warning_schema": {
                "type": "object",
                "properties": {
                    "client": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "minLength": 1}
                        },
                    }
                },
            },
        },
    }
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    data.load_json(
        {
            "SolarProjectId": "unexpected",
            "client_name": "Ada Lovelace",
            "Materials": {
                "batteryBackup": [{"name": "Acme Battery"}],
            },
            "is_battery_only": True,
        },
        save_to_file=False,
    )

    assert data.project.id == "unexpected"
    assert data.client.email == "not-configured@example.invalid"
    assert data.field_provenance["client.email"].used_fallback
    assert data.field_provenance["project.id"].source_path == ("SolarProjectId",)
    assert data.validation_report.errors[0].field == "project.id"
    assert "system.battery.manufacturer" in {
        issue.field for issue in data.validation_report.errors
    }
    assert not data.validation_report.warnings
    assert not data.validation_report.blocks_generation
    assert not data.is_validated

    schema["enforcement"] = "enforce"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(ValueError, match="Data validation") as validation_error:
        data.load_json(
            {
                "SolarProjectId": "unexpected",
                "client_name": "Ada Lovelace",
                "Materials": {
                    "batteryBackup": [{"name": "Acme Battery"}],
                },
                "is_battery_only": True,
            },
            save_to_file=False,
        )
    assert "source=solargraf" in str(validation_error.value)


def test_configured_source_freshness_is_reported_as_a_warning(tmp_path):
    schema_path = tmp_path / "field_schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "version": 1,
                "enforcement": "advisory",
                "validation": {
                    "freshness": {
                        "source_path": ["updatedAt"],
                        "max_age_seconds": 1,
                        "severity": "warning",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    data = DataManager()
    data.field_schema_path = schema_path

    data.load_json(
        {"updatedAt": "2000-01-01T00:00:00Z"},
        save_to_file=False,
    )

    assert data.validation_report.warnings[0].code == "source_stale"
    assert not data.validation_report.blocks_generation


def test_missing_saved_monthly_payment_value_has_actionable_error(tmp_path):
    settings_path = tmp_path / "settings.xlsx"
    settings_workbook = Workbook()
    settings_sheet = settings_workbook.active
    settings_sheet.title = "Spreadsheet"
    for row, cell in enumerate(
        ("A1", "A2", "A3", "A4", "A5", "A6", "A7", "D100"), start=2
    ):
        settings_sheet.cell(row=row, column=2, value=cell)
    settings_workbook.save(settings_path)

    pricing_path = tmp_path / "pricing_spreadsheet.xlsx"
    pricing_workbook = Workbook()
    pricing_sheet = pricing_workbook.active
    pricing_sheet.title = "Pricing Calculator"
    for cell, value in {
        "A1": "No",
        "A2": "Grid-Tied",
        "A3": 0,
        "A4": 0,
        "A5": 0,
        "A6": 25,
        "A7": 0.05,
        "D100": "=1+1",
    }.items():
        pricing_sheet[cell] = value
    pricing_workbook.save(pricing_path)

    data = DataManager()
    data.files.settings = settings_path
    data.files.pricing_spreadsheet = pricing_path

    with pytest.raises(ValueError) as error:
        data.update_from_pricing_spreadsheet()

    message = str(error.value)
    assert "Pricing Calculator!D100" in message
    assert "Ctrl+Alt+F9" in message
    assert "save it" in message
