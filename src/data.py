"""Project data models, source provenance, validation, and workbook inputs."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
import os
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from settings import SettingsManager
from field_schema import (
    DEFAULT_SOURCE_PATHS,
    FieldProvenance,
    ValidationReport,
    load_field_schema,
    validate_instance,
)


_UNSET = object()
_LOAN_TERM_ENV = os.getenv("LOAN_TERM")
_LOAN_INTEREST_RATE_ENV = os.getenv("LOAN_INTEREST_RATE")


@dataclass(frozen=True)
class ProposalPdfMetrics:
    """Key sizing and usage metrics extracted from a proposal PDF."""

    system_size_kw: float
    annual_production_kwh: float
    usage_percentage: float


_MODEL_FIELD_NAMES = (
    "project.id",
    "project.api_id",
    "project.financial_id",
    "project.proposal_id",
    "project.name",
    "client.first_name",
    "client.last_name",
    "client.name",
    "client.phone",
    "client.email",
    "client.address.street",
    "client.address.city",
    "client.address.region_code",
    "client.address.postal_code",
    "utility.name",
    "utility.annual_consumption",
    "system.type",
    "system.ess_type",
    "system.pv_size",
    "system.ess_size",
    "system.panel.manufacturer",
    "system.panel.model",
    "system.panel.type",
    "system.panel.size",
    "system.panel.warranty",
    "system.panel.ptc",
    "system.panel.count",
    "system.panel.specsheet_url",
    "system.inverter.manufacturer",
    "system.inverter.model",
    "system.inverter.efficiency",
    "system.inverter.warranty",
    "system.inverter.count",
    "system.inverter.specsheet_url",
    "system.battery.manufacturer",
    "system.battery.model",
    "system.battery.capacity",
    "system.battery.warranty",
    "system.battery.count",
    "system.battery.specsheet_url",
    "system.annual_production",
    "system.tree_trimming_required",
    "pricing.id",
    "pricing.pv_cost",
    "pricing.ess_cost",
    "pricing.total_cost",
    "pricing.cost_per_watt",
    "pricing.loan_term",
    "pricing.loan_interest_rate",
    "pricing.loan_monthly_payment",
)


class DataManager:
    """Load project data and coordinate its models, sources, and validation."""

    def __init__(self):
        """Initialize project models, schema validation, and provenance state."""
        self.data = {}
        self.proposal_pdf_metrics: ProposalPdfMetrics | None = None
        self.settings = SettingsManager()
        self.field_schema_path = Path(__file__).with_name("field_schema.json")
        self.field_schema = load_field_schema(self.field_schema_path)
        self.field_provenance: dict[str, FieldProvenance] = {}
        self.source_loaded_at: datetime | None = None
        self.validation_report = ValidationReport(
            enforcement=self.field_schema.enforcement
        )
        self._record_default_provenance()
        self._record_environment_provenance()
        self.project = self.Project()
        self.client = self.Client()
        self.utility = self.Utility()
        self.system = self.System()
        self.pricing = self.Pricing()
        self.files = self.Files()
        self.references = self.References()

    def load_json(self, json_data: dict, save_to_file: bool = True):
        """Load a SolarGraf payload, derive model values, validate, and optionally save it."""
        self.proposal_pdf_metrics = None
        self.field_schema = load_field_schema(self.field_schema_path)
        previous_provenance = self.field_provenance.copy()
        self.field_provenance = {}
        self._record_default_provenance()
        self.field_provenance.update(previous_provenance)
        self._record_environment_provenance()
        self.source_loaded_at = datetime.now(timezone.utc)
        self.data = json_data
        self.project.id = self._get_field("project.id", default=0)
        self.project.api_id = self._get_field("project.api_id", default="")
        self.files.modules_spreadsheet = (
            self.settings.files.templates_folder / "modules.xlsx"
        )

        self.client.name = self._get_field("client.name", default="")
        name_parts = self.client.name.split()
        self.client.first_name = name_parts[0] if name_parts else ""
        self.client.last_name = " ".join(name_parts[1:])
        self._record_derived(
            "client.first_name", "client.name", "first name from customer name"
        )
        self._record_derived(
            "client.last_name", "client.name", "last name from customer name"
        )
        self.client.phone = self._get_field("client.phone", default="")
        self.client.email = self._get_field("client.email", default="")
        self.client.address.street = self._get_field(
            "client.address.street", default=""
        )
        self.client.address.city = self._get_field("client.address.city", default="")
        self.client.address.region_code = self._get_field(
            "client.address.region_code", default=""
        )
        self.client.address.postal_code = self._get_field(
            "client.address.postal_code", default=""
        )

        self.project.name = self.client.name.upper()
        self._record_derived("project.name", "client.name", "uppercase project name")

        self.system.type = self._get_system_type()
        self.system.pv_size = self._get_field("system.pv_size")
        self.system.panel.manufacturer = self._get_field(
            "system.panel.manufacturer"
        )
        self.system.panel.model = self._get_field("system.panel.model")
        self.system.panel.type = self._get_field("system.panel.type")
        self.system.panel.size = self._get_field("system.panel.size")
        self.system.panel.ptc = self._get_panel_ptc()
        self.system.panel.warranty = self._get_field("system.panel.warranty")
        self.system.panel.count = self._get_field("system.panel.count", default=0)
        self.system.panel.specsheet_url = self._get_field(
            "system.panel.specsheet_url"
        )

        self.utility.name = self._get_field("utility.name", default="")
        self.utility.annual_consumption = self._calculate_annual_consumption(
            self._get_field("utility.bills", default="")
        )
        self._record_derived(
            "utility.annual_consumption",
            "utility.bills",
            "sum of bill consumptionInKwh values",
        )

        self.system.inverter.manufacturer = self._get_field(
            "system.inverter.manufacturer"
        )
        self.system.inverter.model = self._get_field("system.inverter.model")
        self.system.inverter.warranty = self._get_field("system.inverter.warranty")
        self.system.inverter.count = self._get_field(
            "system.inverter.count", default=0
        )
        self.system.inverter.specsheet_url = self._get_field(
            "system.inverter.specsheet_url"
        )

        self.system.battery.manufacturer = self._get_field(
            "system.battery.manufacturer"
        )
        self.system.battery.model = self._get_field("system.battery.model")
        self.system.battery.capacity = self._get_field("system.battery.capacity")
        self.system.battery.warranty = self._get_field("system.battery.warranty")
        self.system.battery.count = self._get_field(
            "system.battery.count", default=0
        )
        self.system.battery.specsheet_url = self._get_field(
            "system.battery.specsheet_url"
        )

        self.system.ess_size = (
            self.system.battery.capacity * self.system.battery.count
            if self.system.battery.capacity and self.system.battery.count
            else 0.0
        )
        self._record_derived(
            "system.ess_size",
            "system.battery.capacity",
            "system.battery.count",
            "battery capacity multiplied by count",
        )

        self.project.financial_id = self._get_field("project.financial_id")
        self.project.proposal_id = self._get_field("project.proposal_id")

        self.files.settings = self.settings.files.templates_folder / "settings.xlsx"
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

        self.validation_report = self.validate_fields()
        if self.validation_report.blocks_generation:
            raise ValueError(self.format_validation_report())

        if save_to_file:
            self.files.project_folder.mkdir(parents=True, exist_ok=True)
            self.files.images_folder.mkdir(parents=True, exist_ok=True)
            self.files.documents_folder.mkdir(parents=True, exist_ok=True)
            self.files.specsheets_folder.mkdir(parents=True, exist_ok=True)

            with open(self.files.project_folder / "data.json", "w") as f:
                json.dump(self.data, f, indent=4)

    def set_api_id(self, api_id):
        """Set the SolarGraf API identifier and record its application origin."""
        self.project.api_id = api_id
        self.record_provenance(
            "project.api_id",
            FieldProvenance(
                source="application",
                transformation="set through authentication flow",
            ),
        )

    def record_provenance(
        self, field_name: str, provenance: FieldProvenance
    ) -> None:
        """Associate source and transformation details with a model field."""
        self.field_provenance[field_name] = provenance

    def _record_environment_provenance(self) -> None:
        """Record whether loan defaults came from environment variables."""
        for field_name, environment_name, environment_value in (
            ("pricing.loan_term", "LOAN_TERM", _LOAN_TERM_ENV),
            (
                "pricing.loan_interest_rate",
                "LOAN_INTEREST_RATE",
                _LOAN_INTEREST_RATE_ENV,
            ),
        ):
            self.record_provenance(
                field_name,
                FieldProvenance(
                    source="environment" if environment_value is not None else "fallback",
                    source_path=(environment_name,),
                    used_fallback=environment_value is None,
                ),
            )

    def _record_default_provenance(self) -> None:
        """Mark every known model field as initially using a fallback."""
        for field_name in _MODEL_FIELD_NAMES:
            self.record_provenance(
                field_name,
                FieldProvenance(source="fallback", used_fallback=True),
            )

    def provenance_report(self) -> dict[str, dict[str, Any]]:
        """Return serialized provenance for all fields with recorded origins."""
        return {
            field_name: provenance.to_dict()
            for field_name, provenance in self.field_provenance.items()
        }

    def format_validation_report(self) -> str:
        """Format validation issues with each field's source details."""
        lines = [
            f"Data validation (enforcement={self.validation_report.enforcement}):"
        ]
        for issue in (
            self.validation_report.errors + self.validation_report.warnings
        ):
            provenance = self.field_provenance.get(issue.field)
            origin = ""
            if provenance is not None:
                origin = f"; source={provenance.source}"
                if provenance.source_path:
                    origin += f"; source_path={list(provenance.source_path)}"
                if provenance.used_fallback:
                    origin += "; fallback used"
            lines.append(
                f"{issue.severity.upper()} {issue.field}: {issue.message}{origin}"
            )
        return "\n".join(lines)

    def validate_fields(self) -> ValidationReport:
        """Validate the current model against the loaded field schema."""
        report = validate_instance(
            self._validation_data(),
            self.field_schema,
            self.data,
            self.source_loaded_at or datetime.now(timezone.utc),
        )
        self.validation_report = report
        return report

    @property
    def is_validated(self) -> bool:
        """Return whether current project fields have no validation errors."""
        return self.validate_fields().is_valid

    def _validation_data(self) -> dict[str, Any]:
        """Build the nested model dictionary consumed by schema validation."""
        return {
            "project": asdict(self.project),
            "client": {
                "first_name": self.client.first_name,
                "last_name": self.client.last_name,
                "name": self.client.name,
                "phone": self.client.phone,
                "email": self.client.email,
                "address": asdict(self.client.address),
            },
            "utility": asdict(self.utility),
            "system": {
                "type": self.system.type,
                "ess_type": self.system.ess_type,
                "pv_size": self.system.pv_size,
                "ess_size": self.system.ess_size,
                "panel": asdict(self.system.panel),
                "inverter": asdict(self.system.inverter),
                "battery": asdict(self.system.battery),
                "annual_production": self.system.annual_production,
                "tree_trimming_required": self.system.tree_trimming_required,
            },
            "pricing": {
                name: getattr(self.pricing, name)
                for name in (
                    "id",
                    "pv_cost",
                    "ess_cost",
                    "total_cost",
                    "cost_per_watt",
                    "loan_term",
                    "loan_interest_rate",
                    "loan_monthly_payment",
                )
            },
        }

    def _get_field(self, field_name: str, default: Any = _UNSET) -> Any:
        """Read a configured source field and record its fallback provenance."""
        source_path = self.field_schema.source_paths.get(field_name)
        if source_path is None:
            source_path = DEFAULT_SOURCE_PATHS.get(field_name)
        if source_path is None:
            raise KeyError(f"No SolarGraf source path is defined for {field_name}")

        if field_name in self.field_schema.defaults:
            field_default = self.field_schema.defaults[field_name]
        else:
            field_default = None if default is _UNSET else default

        value, used_fallback = self._lookup(self.data, source_path, field_default)
        self.record_provenance(
            field_name,
            FieldProvenance(
                source="fallback" if used_fallback else "solargraf",
                source_path=source_path,
                used_fallback=used_fallback,
            ),
        )
        return value

    def _record_spreadsheet_provenance(
        self, field_name: str, worksheet: str, cell: str
    ) -> None:
        """Record a value's workbook, worksheet, and cell origin."""
        self.record_provenance(
            field_name,
            FieldProvenance(
                source="pricing_spreadsheet",
                source_path=(str(self.files.pricing_spreadsheet), worksheet, cell),
            ),
        )

    def _record_derived(self, field_name: str, *inputs_and_transformation: str) -> None:
        """Record the input fields and transformation used to derive a value."""
        *input_fields, transformation = inputs_and_transformation
        input_provenance = [
            self.field_provenance[name]
            for name in input_fields
            if name in self.field_provenance
        ]
        source_path = (
            input_provenance[0].source_path
            if len(input_provenance) == 1
            else None
        )
        self.record_provenance(
            field_name,
            FieldProvenance(
                source="derived",
                source_path=source_path,
                used_fallback=any(item.used_fallback for item in input_provenance),
                transformation=transformation,
                derived_from=tuple(input_fields),
            ),
        )

    def validate_for_document_generation(self, document_kind: str) -> None:
        """Raise a descriptive error when a document prerequisite is missing."""
        report = self.validate_fields()
        if report.blocks_generation:
            raise ValueError(self.format_validation_report())

        required_values = {
            "project ID": self.project.id,
            "SolarGraf project ID": self.project.api_id,
            "proposal ID": self.project.proposal_id,
            "financial ID": self.project.financial_id,
            "client name": self.client.name,
            "client street address": self.client.address.street,
            "client city": self.client.address.city,
            "client region": self.client.address.region_code,
            "client postal code": self.client.address.postal_code,
            "utility": self.utility.name,
        }
        missing = [
            label
            for label, value in required_values.items()
            if value is None or (isinstance(value, str) and not value.strip())
        ]
        if not isinstance(self.project.id, (int, float)) or self.project.id <= 0:
            missing.append("project ID")

        if self.system.type not in (0, 1, 2):
            missing.append("a supported system type")

        if self.system.type in (0, 2):
            required_values = {
                "PV size": self.system.pv_size,
                "panel manufacturer": self.system.panel.manufacturer,
                "panel model": self.system.panel.model,
                "panel size": self.system.panel.size,
                "panel count": self.system.panel.count,
                "inverter manufacturer": self.system.inverter.manufacturer,
                "inverter model": self.system.inverter.model,
                "inverter count": self.system.inverter.count,
            }
            missing.extend(
                label
                for label, value in required_values.items()
                if value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, (int, float)) and value <= 0)
            )

        if self.system.type in (1, 2):
            required_values = {
                "battery manufacturer": self.system.battery.manufacturer,
                "battery model": self.system.battery.model,
                "battery capacity": self.system.battery.capacity,
                "battery count": self.system.battery.count,
            }
            missing.extend(
                label
                for label, value in required_values.items()
                if value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, (int, float)) and value <= 0)
            )

        if document_kind == "final_proposal":
            required_urls = {}
            if self.system.type in (0, 2):
                required_urls.update(
                    {
                        "panel specification-sheet URL": self.system.panel.specsheet_url,
                        "inverter specification-sheet URL": self.system.inverter.specsheet_url,
                    }
                )
            if self.system.type in (1, 2):
                required_urls["battery specification-sheet URL"] = (
                    self.system.battery.specsheet_url
                )
            missing.extend(
                label
                for label, value in required_urls.items()
                if value is None or (isinstance(value, str) and not value.strip())
            )

        required_files = {}
        if document_kind == "pricing":
            required_files = {
                "pricing spreadsheet template": self.files.pricing_spreadsheet_template,
                "settings workbook": self.files.settings,
            }
        elif document_kind == "cover_letter":
            required_files = {
                "cover letter template": self.files.cover_letter_template,
                "settings workbook": self.files.settings,
                "pricing spreadsheet": self.files.pricing_spreadsheet,
            }
        elif document_kind == "proposal_download":
            required_files = {}
        elif document_kind == "final_proposal":
            required_files = {
                "cover letter document": self.files.cover_letter_docx,
                "SolarGraf proposal PDF": self.files.solargraf_proposal,
                "pricing spreadsheet": self.files.pricing_spreadsheet,
                "settings workbook": self.files.settings,
            }
        else:
            raise ValueError(f"Unknown document generation stage: {document_kind}")

        missing.extend(
            label
            for label, path in required_files.items()
            if not path or not Path(path).is_file()
        )

        if missing:
            details = "\n".join(f"- {item}" for item in dict.fromkeys(missing))
            raise ValueError(
                f"Cannot generate {document_kind.replace('_', ' ')} until "
                f"the following prerequisites are provided:\n{details}"
            )

    def _set_annual_production(self, annual_production):
        """Store the annual production value derived from proposal metrics."""
        self.system.annual_production = annual_production

    def _get(self, *keys, default=None) -> Any:
        """Look up a nested payload path and return default when it is absent."""
        value, _ = self._lookup(self.data, keys, default)
        return value

    @staticmethod
    def _lookup(data: Any, keys: Any, default: Any) -> tuple[Any, bool]:
        """Traverse dictionary keys or list indices and report fallback use."""
        try:
            for key in keys:
                if isinstance(key, int):
                    data = data[key]
                else:
                    data = data.get(key)

                if data is None:
                    return default, True
            return data, False
        except (KeyError, IndexError, TypeError):
            return default, True

    @staticmethod
    def _clean_float(value):
        """Convert a value to float, warning and returning zero on failure."""
        try:
            return float(value)
        except (ValueError, TypeError):
            print(
                f"Warning: Unable to convert value '{value}' to float. Returning 0.0 instead."
            )
            return 0.0

    @staticmethod
    def _clean_int(value):
        """Convert a value to int, returning zero when conversion fails."""
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def update_from_pricing_spreadsheet(self):
        """Load settings and pricing workbook values into models and provenance."""
        if self.files.settings.is_file():
            workbook = load_workbook(
                self.files.settings, data_only=True, read_only=True
            )
            sheet = workbook["Spreadsheet"]
            self.references.tree_trimming_required = sheet["B2"].value
            self.references.ess_type = sheet["B3"].value
            self.references.pv_cost = sheet["B4"].value
            self.references.ess_cost = sheet["B5"].value
            self.references.total_cost = sheet["B6"].value
            self.references.loan_term = sheet["B7"].value
            self.references.loan_interest_rate = sheet["B8"].value
            self.references.loan_monthly_payment = sheet["B9"].value
            self.references.panel_ptc = sheet["B10"].value
            self.references.inverter_efficiency = sheet["B11"].value
            workbook.close()
            for reference_name, cell in {
                "tree_trimming_required": "B2",
                "ess_type": "B3",
                "pv_cost": "B4",
                "ess_cost": "B5",
                "total_cost": "B6",
                "loan_term": "B7",
                "loan_interest_rate": "B8",
                "loan_monthly_payment": "B9",
                "panel_ptc": "B10",
                "inverter_efficiency": "B11",
            }.items():
                self.record_provenance(
                    f"references.{reference_name}",
                    FieldProvenance(
                        source="settings_workbook",
                        source_path=(
                            str(self.files.settings),
                            "Spreadsheet",
                            cell,
                        ),
                    ),
                )

        if self.files.pricing_spreadsheet.is_file():
            workbook = load_workbook(
                self.files.pricing_spreadsheet, data_only=True, read_only=True
            )
            sheet = workbook["Pricing Calculator"]
            self.system.tree_trimming_required = sheet[
                self.references.tree_trimming_required
            ].value
            self.system.ess_type = (
                0 if (sheet[self.references.ess_type].value == "Grid-Tied") else 1
            )
            self.pricing.pv_cost = (
                float(sheet[self.references.pv_cost].value)
                if sheet[self.references.pv_cost].value is not None
                else 0.0
            )
            self.pricing.ess_cost = (
                float(sheet[self.references.ess_cost].value)
                if sheet[self.references.ess_cost].value is not None
                else 0.0
            )
            self.pricing.total_cost = (
                float(sheet[self.references.total_cost].value)
                if sheet[self.references.total_cost].value is not None
                else 0.0
            )
            self.pricing.loan_term = int(sheet[self.references.loan_term].value)
            self.pricing.loan_interest_rate = float(
                sheet[self.references.loan_interest_rate].value
            )
            loan_monthly_payment_cell = self.references.loan_monthly_payment
            loan_monthly_payment = sheet[loan_monthly_payment_cell].value
            if loan_monthly_payment is None:
                workbook.close()
                raise ValueError(
                    "The monthly payment cell "
                    f"(Pricing Calculator!{loan_monthly_payment_cell}) in "
                    f"{self.files.pricing_spreadsheet} has no saved calculated "
                    "value. Open the workbook in Excel, recalculate it "
                    "(Ctrl+Alt+F9), save it, and try again. If it is still blank, "
                    "check the loan inputs."
                )
            self.pricing.loan_monthly_payment = math.ceil(loan_monthly_payment)
            self.system.panel.ptc = int(float(sheet[self.references.panel_ptc].value))
            self.system.inverter.efficiency = (
                float(sheet[self.references.inverter_efficiency].value)
                if sheet[self.references.inverter_efficiency].value is not None
                else 0.97
            )
            self.system.panel.count = (
                int(sheet["C12"].value)
                if sheet["C12"].value is not None
                else self.system.panel.count
            )
            self.system.inverter.count = (
                int(sheet["C13"].value)
                if sheet["C13"].value is not None
                else self.system.inverter.count
            )
            self.system.battery.count = (
                int(sheet["C16"].value)
                if sheet["C16"].value is not None
                else self.system.battery.count
            )
            for field_name, cell in (
                ("system.tree_trimming_required", self.references.tree_trimming_required),
                ("system.ess_type", self.references.ess_type),
                ("pricing.pv_cost", self.references.pv_cost),
                ("pricing.ess_cost", self.references.ess_cost),
                ("pricing.total_cost", self.references.total_cost),
                ("pricing.loan_term", self.references.loan_term),
                ("pricing.loan_interest_rate", self.references.loan_interest_rate),
                ("pricing.loan_monthly_payment", self.references.loan_monthly_payment),
                ("system.panel.ptc", self.references.panel_ptc),
                ("system.inverter.efficiency", self.references.inverter_efficiency),
            ):
                if sheet[cell].value is not None:
                    self._record_spreadsheet_provenance(
                        field_name, "Pricing Calculator", str(cell)
                    )
                elif field_name in {
                    "pricing.pv_cost",
                    "pricing.ess_cost",
                    "pricing.total_cost",
                    "system.inverter.efficiency",
                }:
                    self.record_provenance(
                        field_name,
                        FieldProvenance(
                            source="fallback",
                            source_path=(
                                str(self.files.pricing_spreadsheet),
                                "Pricing Calculator",
                                str(cell),
                            ),
                            used_fallback=True,
                            transformation="spreadsheet cell was empty",
                        ),
                    )
            for field_name, cell in (
                ("system.panel.count", "C12"),
                ("system.inverter.count", "C13"),
                ("system.battery.count", "C16"),
            ):
                if sheet[cell].value is not None:
                    self._record_spreadsheet_provenance(
                        field_name, "Pricing Calculator", cell
                    )
            workbook.close()

    def _get_system_type(self):
        """Classify the project as PV, storage-only, or PV with storage."""
        battery_data = self._get_field("system.battery.source", default=None)
        derived_from = ["system.battery.source"]
        if not isinstance(battery_data, dict) or not battery_data:
            system_type = 0
        else:
            roofing_only = self._get_field("system.roofing_only")
            derived_from.append("system.roofing_only")
            if roofing_only:
                system_type = 0
            else:
                battery_only = self._get_field("system.battery_only")
                derived_from.append("system.battery_only")
                system_type = 1 if battery_only else 2
        self._record_derived(
            "system.type",
            *derived_from,
            "system classification from SolarGraf system flags",
        )
        return system_type

    def _calculate_annual_consumption(self, bills):
        """Sum consumptionInKwh values from the project's utility bills."""
        total_consumption = 0.0
        # TODO: Rewrite for real data
        for bill in bills:
            consumption = bill.get("consumptionInKwh", 0.0)
            total_consumption += consumption
        return total_consumption

    def _get_panel_ptc(self) -> int | None:
        """Resolve panel PTC from project data or the module catalog workbook."""
        panel_ptc = self._get_field("system.panel.ptc")
        if panel_ptc is not None and panel_ptc > 0:
            return panel_ptc
        elif self.files.modules_spreadsheet.is_file():
            workbook = load_workbook(
                self.files.modules_spreadsheet, data_only=True, read_only=True
            )
            sheet = workbook["PV Module-Full"]
            for row_number, row in enumerate(
                sheet.iter_rows(min_row=2, values_only=True), start=2
            ):
                model, ptc = row[1], row[5]
                if self.system.panel.model is not None and model is not None:
                    if self.system.panel.model.lower() in str(model).lower():
                        workbook.close()
                        self.record_provenance(
                            "system.panel.ptc",
                            FieldProvenance(
                                source="template",
                                source_path=(
                                    str(self.files.modules_spreadsheet),
                                    "PV Module-Full",
                                    row_number,
                                    "F",
                                ),
                                transformation="lookup by panel model",
                                derived_from=("system.panel.model",),
                            ),
                        )
                        return ptc
            workbook.close()
        self.record_provenance(
            "system.panel.ptc",
            FieldProvenance(
                source="fallback",
                source_path=self.field_schema.source_paths.get(
                    "system.panel.ptc",
                    DEFAULT_SOURCE_PATHS["system.panel.ptc"],
                ),
                used_fallback=True,
                transformation="no valid SolarGraf or template PTC value",
                derived_from=("system.panel.model",),
            ),
        )
        return None

    @dataclass
    class Project:
        """Project identifiers and display name."""

        id: int = 0
        api_id: str = ""
        financial_id: str = ""
        proposal_id: str = ""
        name: str = ""

    class Client:
        """Customer contact details and service address."""

        def __init__(self):
            """Initialize customer fields and a nested address model."""
            self.first_name: str = ""
            self.last_name: str = ""
            self.name: str = ""
            self.phone: str = ""
            self.email: str = ""
            self.address = self.Address()

        @dataclass
        class Address:
            """Customer's street, city, region, and postal code."""

            street: str = ""
            city: str = ""
            region_code: str = ""
            postal_code: str = ""

    @dataclass
    class Utility:
        """Utility name and annual customer energy consumption."""

        name: str = ""
        annual_consumption: float = 0.0

    @dataclass
    class System:
        """PV and energy-storage system configuration."""

        def __init__(self):
            """Initialize system properties and nested component models."""
            self.type: int = 0
            self.ess_type: int = 0
            self.pv_size: float = 0.0
            self.ess_size: float = 0.0
            self.panel = self.Panel()
            self.inverter = self.Inverter()
            self.battery = self.Battery()
            self.annual_production: float = 0.0
            self.tree_trimming_required: bool = False

        @dataclass
        class Panel:
            """Solar panel product, rating, count, and specification sheet."""

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
            """Inverter product, efficiency, count, and specification sheet."""

            manufacturer: str = ""
            model: str = ""
            efficiency: float = 0.0
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""

        @dataclass
        class Battery:
            """Battery product, capacity, count, and specification sheet."""

            manufacturer: str = ""
            model: str = ""
            capacity: float = 0.0
            warranty: int = 0
            count: int = 0
            specsheet_url: str = ""

    @dataclass
    class Pricing:
        """Proposal pricing and loan calculation values."""

        id: str = ""
        pv_cost = 0.0
        ess_cost: float = 0.0
        total_cost: float = 0.0
        cost_per_watt: float = 0.0
        loan_term: int = int(_LOAN_TERM_ENV if _LOAN_TERM_ENV is not None else "0")
        loan_interest_rate: float = float(
            _LOAN_INTEREST_RATE_ENV
            if _LOAN_INTEREST_RATE_ENV is not None
            else "0.0"
        )
        loan_monthly_payment: float = 0

    @dataclass
    class Files:
        """Paths to project directories, templates, and generated documents."""

        pricing_spreadsheet_template: Path = Path()
        cover_letter_template: Path = Path()
        solargraf_proposal_template: Path = Path()
        modules_spreadsheet: Path = Path()
        settings: Path = Path()
        email_template: Path = Path()
        project_folder: Path = Path()
        images_folder: Path = Path()
        documents_folder: Path = Path()
        specsheets_folder: Path = Path()
        proposal_package_folder: Path = Path()
        proposal_manifest: Path = Path()
        solargraf_proposal: Path = Path()
        pricing_spreadsheet: Path = Path()
        cover_letter_docx: Path = Path()
        cover_letter_pdf: Path = Path()
        final_proposal: Path = Path()

    @dataclass
    class References:
        """Settings-workbook cell references used by spreadsheet import."""

        tree_trimming_required: str = ""
        ess_type: str = ""
        pv_cost: str = ""
        ess_cost: str = ""
        total_cost: str = ""
        loan_term: str = ""
        loan_interest_rate: str = ""
        loan_monthly_payment: str = ""
        panel_ptc: str = ""
        inverter_efficiency: str = ""
