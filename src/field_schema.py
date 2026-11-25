"""Field provenance models and configurable project-data validation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


DEFAULT_SOURCE_PATHS: dict[str, tuple[str | int, ...]] = {
    "project.id": ("id",),
    "project.api_id": ("public_id",),
    "client.name": ("client_name",),
    "client.phone": ("client_phone",),
    "client.email": ("client_email",),
    "client.address.street": ("Position", "street"),
    "client.address.city": ("Position", "city"),
    "client.address.region_code": ("Position", "region_code"),
    "client.address.postal_code": ("Position", "postal_code"),
    "system.pv_size": ("proposals", 0, "sizeInKw"),
    "system.panel.manufacturer": ("Materials", "panel", 0, "Manufacturer", "name"),
    "system.panel.model": ("Materials", "panel", 0, "name"),
    "system.panel.type": ("Materials", "panel", 0, "type"),
    "system.panel.size": ("Materials", "panel", 0, "size_in_watts"),
    "system.panel.ptc": ("Materials", "panel", 0, "ptc"),
    "system.panel.warranty": ("Materials", "panel", 0, "warranty"),
    "system.panel.count": ("Materials", "panel", 0, "count"),
    "system.panel.specsheet_url": ("Materials", "panel", 0, "spec_sheet"),
    "utility.name": (
        "Settings",
        "Pricing",
        "ProjectConnection",
        "genability_lse_name",
    ),
    "utility.bills": ("Settings", "Pricing", "ProjectConnection", "Bills"),
    "system.inverter.manufacturer": (
        "Materials",
        "inverter",
        0,
        "Manufacturer",
        "name",
    ),
    "system.inverter.model": ("Materials", "inverter", 0, "name"),
    "system.inverter.warranty": ("Materials", "inverter", 0, "warranty"),
    "system.inverter.count": ("Materials", "inverter", 0, "count"),
    "system.inverter.specsheet_url": ("Materials", "inverter", 0, "spec_sheet"),
    "system.battery.manufacturer": (
        "Materials",
        "batteryBackup",
        0,
        "Manufacturer",
        "name",
    ),
    "system.battery.model": ("Materials", "batteryBackup", 0, "name"),
    "system.battery.capacity": ("Materials", "batteryBackup", 0, "capacity"),
    "system.battery.warranty": ("Materials", "batteryBackup", 0, "warranty"),
    "system.battery.count": ("Materials", "batteryBackup", 0, "count"),
    "system.battery.specsheet_url": (
        "Materials",
        "batteryBackup",
        0,
        "spec_sheet",
    ),
    "system.battery.source": ("Materials", "batteryBackup", 0),
    "system.roofing_only": ("is_roofing_only",),
    "system.battery_only": ("is_battery_only",),
    "project.financial_id": ("Settings", "Pricing", "FinancialOptions", 0, "id"),
    "project.proposal_id": (
        "Settings",
        "Pricing",
        "ProjectConnection",
        "proposal_id",
    ),
}


@dataclass(frozen=True)
class FieldProvenance:
    """Describe the origin and transformation history of one field value."""

    source: str
    source_path: tuple[str | int, ...] | None = None
    used_fallback: bool = False
    transformation: str | None = None
    derived_from: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize provenance into JSON-compatible values."""
        return {
            "source": self.source,
            "source_path": list(self.source_path) if self.source_path else None,
            "used_fallback": self.used_fallback,
            "transformation": self.transformation,
            "derived_from": list(self.derived_from),
        }


@dataclass(frozen=True)
class ValidationIssue:
    """Represent one field validation error or warning."""

    severity: str
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize the issue into a JSON-compatible dictionary."""
        return {
            "severity": self.severity,
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidationReport:
    """Collect schema issues and report whether they block generation."""

    enforcement: str = "advisory"
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Return whether the report contains no errors."""
        return not self.errors

    @property
    def blocks_generation(self) -> bool:
        """Return whether enforced validation errors prevent generation."""
        return self.enforcement == "enforce" and not self.is_valid

    def to_dict(self) -> dict[str, Any]:
        """Serialize report status, errors, and warnings."""
        return {
            "enforcement": self.enforcement,
            "is_valid": self.is_valid,
            "blocks_generation": self.blocks_generation,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
        }

    def format(self) -> str:
        """Format all issues as newline-separated field messages."""
        lines = [
            f"{issue.field}: {issue.message}" for issue in self.errors + self.warnings
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class FieldSchema:
    """Hold source mappings, defaults, validation rules, and freshness policy."""

    enforcement: str
    source_paths: dict[str, tuple[str | int, ...]]
    defaults: dict[str, Any]
    blocking_schema: dict[str, Any]
    warning_schema: dict[str, Any]
    freshness: dict[str, Any] | None


def load_field_schema(path: Path) -> FieldSchema:
    """Load and validate the field-schema JSON file at path."""
    if not path.is_file():
        return FieldSchema(
            enforcement="advisory",
            source_paths={},
            defaults={},
            blocking_schema={"type": "object"},
            warning_schema={"type": "object"},
            freshness=None,
        )

    try:
        contents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unable to read field schema {path}: {exc}") from exc

    if (
        not isinstance(contents, dict)
        or not isinstance(contents.get("version"), int)
        or isinstance(contents.get("version"), bool)
        or contents.get("version") != 1
    ):
        raise ValueError("Field schema must be a version 1 JSON object")

    enforcement = contents.get("enforcement", "advisory")
    if not isinstance(enforcement, str) or enforcement not in {
        "advisory",
        "enforce",
    }:
        raise ValueError("Field schema enforcement must be 'advisory' or 'enforce'")

    source_paths = _parse_source_paths(contents.get("source_paths", {}))
    defaults = contents.get("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("Field schema defaults must be a JSON object")

    validation = contents.get("validation", {})
    if not isinstance(validation, dict):
        raise ValueError("Field schema validation must be a JSON object")
    blocking_schema = validation.get("blocking_schema", {"type": "object"})
    warning_schema = validation.get("warning_schema", {"type": "object"})
    for schema in (blocking_schema, warning_schema):
        if not isinstance(schema, dict):
            raise ValueError("Field validation schemas must be JSON objects")
        Draft202012Validator.check_schema(schema)

    freshness = validation.get("freshness")
    if freshness is not None:
        if not isinstance(freshness, dict):
            raise ValueError("Field schema freshness must be a JSON object")
        freshness_path = _parse_path(freshness.get("source_path"), "freshness.source_path")
        max_age = freshness.get("max_age_seconds")
        severity = freshness.get("severity", "warning")
        if (
            not isinstance(max_age, (int, float))
            or isinstance(max_age, bool)
            or max_age < 0
        ):
            raise ValueError("Freshness max_age_seconds must be a non-negative number")
        if not isinstance(severity, str) or severity not in {"error", "warning"}:
            raise ValueError("Freshness severity must be 'error' or 'warning'")
        freshness = {
            "source_path": freshness_path,
            "max_age_seconds": max_age,
            "severity": severity,
        }

    return FieldSchema(
        enforcement=enforcement,
        source_paths=source_paths,
        defaults=defaults,
        blocking_schema=blocking_schema,
        warning_schema=warning_schema,
        freshness=freshness,
    )


def schema_issues(
    instance: dict[str, Any], schema: dict[str, Any], severity: str
) -> list[ValidationIssue]:
    """Validate an instance and convert sorted schema failures into issues."""
    validator = Draft202012Validator(
        schema, format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    issues = []
    for error in sorted(
        validator.iter_errors(instance),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        if error.validator == "required" and isinstance(error.instance, dict):
            missing_fields = [
                name for name in error.validator_value if name not in error.instance
            ]
            for name in missing_fields:
                field_path = ".".join(
                    str(part) for part in (*error.absolute_path, name)
                )
                issues.append(
                    ValidationIssue(
                        severity=severity,
                        field=field_path,
                        code="required",
                        message=f"{name!r} is a required property",
                    )
                )
            continue

        field_path = ".".join(str(part) for part in error.absolute_path) or "$"
        message = error.message
        if isinstance(error.schema, dict) and error.schema.get("x-unit"):
            message += f" (unit: {error.schema['x-unit']})"
        issues.append(
            ValidationIssue(
                severity=severity,
                field=field_path,
                code=str(error.validator or "schema"),
                message=message,
            )
        )
    return issues


def validate_instance(
    instance: dict[str, Any],
    schema: FieldSchema,
    source_payload: dict[str, Any],
    now: datetime,
) -> ValidationReport:
    """Apply configured schemas and source-timestamp freshness validation."""
    report = ValidationReport(enforcement=schema.enforcement)
    report.errors.extend(
        schema_issues(instance, schema.blocking_schema, severity="error")
    )
    report.warnings.extend(
        schema_issues(instance, schema.warning_schema, severity="warning")
    )

    if schema.freshness is not None:
        timestamp = _lookup_source_path(
            source_payload, schema.freshness["source_path"]
        )
        issue = _freshness_issue(timestamp, schema.freshness, now)
        if issue is not None:
            if issue.severity == "error":
                report.errors.append(issue)
            else:
                report.warnings.append(issue)
    return report


def _freshness_issue(
    value: Any, freshness: dict[str, Any], now: datetime
) -> ValidationIssue | None:
    """Return a missing, invalid, or stale timestamp issue when applicable."""
    source_path = freshness["source_path"]
    field_path = ".".join(str(part) for part in source_path)
    if value is None:
        return ValidationIssue(
            severity=freshness["severity"],
            field=field_path,
            code="source_freshness_missing",
            message="Source timestamp is missing",
        )
    if not isinstance(value, str):
        return ValidationIssue(
            severity=freshness["severity"],
            field=field_path,
            code="source_freshness_invalid",
            message="Source timestamp must be an ISO 8601 string",
        )
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ValidationIssue(
            severity=freshness["severity"],
            field=field_path,
            code="source_freshness_invalid",
            message="Source timestamp must be an ISO 8601 string",
        )
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    age_seconds = (now - timestamp).total_seconds()
    if age_seconds > freshness["max_age_seconds"]:
        return ValidationIssue(
            severity=freshness["severity"],
            field=field_path,
            code="source_stale",
            message=(
                f"Source timestamp is older than "
                f"{freshness['max_age_seconds']} seconds"
            ),
        )
    return None


def _lookup_source_path(
    source: dict[str, Any], path: tuple[str | int, ...]
) -> Any:
    """Read a nested source value, returning None when a path is absent."""
    value: Any = source
    try:
        for segment in path:
            value = value[segment]
    except (KeyError, IndexError, TypeError):
        return None
    return value


def _parse_source_paths(value: Any) -> dict[str, tuple[str | int, ...]]:
    """Validate and normalize the configured field-to-source path mapping."""
    if not isinstance(value, dict):
        raise ValueError("Field schema source_paths must be a JSON object")
    paths = {}
    for field_name, source_path in value.items():
        if not isinstance(field_name, str) or not field_name:
            raise ValueError("Field schema source path names must be non-empty strings")
        paths[field_name] = _parse_path(source_path, field_name)
    return paths


def _parse_path(value: Any, label: str) -> tuple[str | int, ...]:
    """Validate a non-empty path array and return it as a tuple."""
    if not isinstance(value, list) or not value:
        raise ValueError(f"Field schema path for {label} must be a non-empty array")
    if any(
        not isinstance(part, (str, int)) or isinstance(part, bool) for part in value
    ):
        raise ValueError(f"Field schema path for {label} contains an invalid segment")
    return tuple(value)
