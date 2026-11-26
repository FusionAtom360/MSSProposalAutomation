"""Generate, validate, publish, and email proposal documents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
import win32com.client as win32
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Mapping
from openpyxl import load_workbook
from docx import Document
import docx2pdf
from pypdf import PdfReader, PdfWriter
from scraper import Scraper
from data import DataManager
from settings import SettingsManager


def _validate_pdf(path: Path) -> int:
    """Validate a non-empty, unencrypted PDF and return its page count."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"PDF is missing or empty: {path}")

    try:
        reader = PdfReader(str(path), strict=True)
        if reader.is_encrypted:
            raise ValueError(f"Encrypted PDFs are not supported: {path}")
        page_count = len(reader.pages)
    except Exception as exc:
        raise ValueError(f"Invalid PDF: {path}") from exc

    if page_count == 0:
        raise ValueError(f"PDF contains no pages: {path}")
    return page_count


def _fsync_file(path: Path) -> None:
    """Flush a file's contents to storage."""
    with path.open("r+b") as file:
        os.fsync(file.fileno())


def _copy_file_fsynced(source: str | Path, destination: str | Path) -> str | Path:
    """Copy a file and flush its contents before returning the destination."""
    with Path(source).open("rb") as source_file:
        with Path(destination).open("wb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)
            destination_file.flush()
            os.fsync(destination_file.fileno())
    return destination


def _sha256(path: Path) -> str:
    """Compute a file's SHA-256 digest in bounded-size chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, relative_to: Path | None = None) -> dict[str, Any]:
    """Return path, byte-size, and digest metadata for a file."""
    return {
        "path": str(path.relative_to(relative_to)) if relative_to else str(path),
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


class OfficeDocumentManager:
    """Create proposal documents and publish complete proposal packages."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        """Set the application, template, and document directories."""
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.templates_dir = self.base_dir / "templates"
        self.documents_dir = self.base_dir / "documents"
        self.alias_mapping: dict[str, str] = {}

    def complete_pricing_spreadsheet(self, data: DataManager, variables) -> Path:
        """Validate inputs, substitute placeholders, and save the pricing workbook."""
        data.validate_for_document_generation("pricing")

        variables.update(data)
        workbook = load_workbook(data.files.pricing_spreadsheet_template)

        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value and isinstance(cell.value, str):
                        for placeholder, replacement in variables.get_all().items():
                            if placeholder in str(cell.value):
                                try:
                                    int(replacement)
                                    cell.value = int(
                                        cell.value.replace(
                                            placeholder, str(replacement)
                                        )
                                    )
                                except (ValueError, TypeError):
                                    cell.value = cell.value.replace(
                                        placeholder, str(replacement)
                                    )

        workbook.save(data.files.pricing_spreadsheet)
        workbook.close()
        return data.files.pricing_spreadsheet

    def complete_cover_letter(self, data: DataManager, variables) -> Path:
        """Populate and save the configured cover-letter DOCX template."""
        data.validate_for_document_generation("cover_letter")
        data.update_from_pricing_spreadsheet()
        variables.update(data)
        document = Document(str(data.files.cover_letter_template))

        for paragraph in document.paragraphs:
            self._replace_in_paragraph(paragraph, variables.get_all())

        document.save(str(data.files.cover_letter_docx))
        return data.files.cover_letter_docx

    def finalize_proposal(self, data: DataManager, variables, scraper: Scraper) -> Path:
        """Build a staged PDF package, manifest it, and publish it atomically."""
        data.validate_for_document_generation("final_proposal")
        documents_dir = Path(data.files.documents_folder)
        if documents_dir == Path("."):
            previous_package = Path(data.files.proposal_package_folder)
            documents_dir = (
                previous_package.parent.parent
                if previous_package != Path(".")
                else Path(data.files.final_proposal).parent
            )
        documents_dir.mkdir(parents=True, exist_ok=True)
        run_id = (
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
            f"{uuid.uuid4().hex}"
        )
        staging_root = documents_dir / ".proposal-staging"
        package_root = documents_dir / "proposal_packages"
        staging_root.mkdir(parents=True, exist_ok=True)
        package_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root / run_id
        package_dir = package_root / run_id
        staging_dir.mkdir()

        source_inputs = {
            "cover_letter_docx": Path(data.files.cover_letter_docx),
            "solargraf_proposal_pdf": Path(data.files.solargraf_proposal),
            "pricing_spreadsheet": Path(data.files.pricing_spreadsheet),
            "settings_workbook": Path(data.files.settings),
        }

        try:
            input_dir = staging_dir / "inputs"
            input_dir.mkdir()
            snapshots = {}
            for name, source in source_inputs.items():
                snapshot = input_dir / f"{name}{source.suffix}"
                shutil.copyfile(source, snapshot)
                _fsync_file(snapshot)
                snapshots[name] = snapshot

            source_proposal_pages = _validate_pdf(snapshots["solargraf_proposal_pdf"])
            cover_letter_pdf = staging_dir / "cover_letter.pdf"
            converted_pdf = staging_dir / "cover_letter.converted.pdf"
            docx2pdf.convert(str(snapshots["cover_letter_docx"]), str(converted_pdf))
            cover_letter_pages = _validate_pdf(converted_pdf)
            _fsync_file(converted_pdf)
            os.replace(converted_pdf, cover_letter_pdf)

            specsheet_pages = {}
            workbook = load_workbook(
                snapshots["settings_workbook"], data_only=True, read_only=True
            )
            try:
                sheet = workbook["Spec Sheets"]
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    model, value = row[0], row[1]
                    if model and value is not None:
                        if model == variables.resolve(r"{{PANEL_MODEL}}"):
                            specsheet_pages["panel"] = self._parse_page_limit(
                                value, "panel"
                            )
                        elif model == variables.resolve(r"{{INVERTER_MODEL}}"):
                            specsheet_pages["inverter"] = self._parse_page_limit(
                                value, "inverter"
                            )
                        elif model == variables.resolve(r"{{BATTERY_MODEL}}"):
                            specsheet_pages["battery"] = self._parse_page_limit(
                                value, "battery"
                            )
            finally:
                workbook.close()

            specsheets_dir = staging_dir / "specsheets"
            downloads_dir = staging_dir / "downloads"
            specsheets_dir.mkdir()
            downloads_dir.mkdir()
            requested_specsheets: list[tuple[str, str]] = []
            if data.system.type in (0, 2):
                requested_specsheets.extend(
                    (
                        ("panel", data.system.panel.specsheet_url),
                        ("inverter", data.system.inverter.specsheet_url),
                    )
                )
            if data.system.type in (1, 2):
                requested_specsheets.append(
                    ("battery", data.system.battery.specsheet_url)
                )

            specsheet_files = []
            specsheet_page_counts = {}
            for name, url in requested_specsheets:
                downloaded_path = Path(scraper.download(url, output_dir=downloads_dir))
                _validate_pdf(downloaded_path)
                target = specsheets_dir / f"{name}.pdf"
                max_pages = specsheet_pages.get(name)
                if max_pages is None:
                    shutil.copyfile(
                        downloaded_path, target.with_name(f"{name}.tmp.pdf")
                    )
                else:
                    if max_pages <= 0:
                        raise ValueError(
                            f"Configured page count for {name} must be positive."
                        )
                    reader = PdfReader(str(downloaded_path), strict=True)
                    spec_writer = PdfWriter()
                    for page in reader.pages[:max_pages]:
                        spec_writer.add_page(page)
                    spec_writer.write(str(target.with_name(f"{name}.tmp.pdf")))

                temporary_spec = target.with_name(f"{name}.tmp.pdf")
                specsheet_page_counts[name] = _validate_pdf(temporary_spec)
                _fsync_file(temporary_spec)
                os.replace(temporary_spec, target)
                specsheet_files.append(target)

            shutil.rmtree(downloads_dir)

            final_pdf = staging_dir / "final_proposal.pdf"
            temporary_final = staging_dir / "final_proposal.tmp.pdf"
            writer = PdfWriter()
            writer.append(str(cover_letter_pdf))
            writer.append(str(snapshots["solargraf_proposal_pdf"]))
            for specsheet_file in specsheet_files:
                writer.append(str(specsheet_file))
            writer.write(str(temporary_final))
            final_page_count = _validate_pdf(temporary_final)
            _fsync_file(temporary_final)
            os.replace(temporary_final, final_pdf)

            supporting_dir = staging_dir / "supporting"
            supporting_dir.mkdir()
            support_files = {}
            for name in (
                "cover_letter_docx",
                "solargraf_proposal_pdf",
                "pricing_spreadsheet",
            ):
                source = snapshots[name]
                target = supporting_dir / source.name
                shutil.copyfile(source, target)
                _fsync_file(target)
                support_files[name] = target

            input_records = {
                name: {
                    "source_path": str(source.resolve()),
                    "snapshot_size_bytes": snapshots[name].stat().st_size,
                    "snapshot_sha256": _sha256(snapshots[name]),
                }
                for name, source in source_inputs.items()
            }
            shutil.rmtree(input_dir)
            artifacts = [
                {
                    **_file_record(cover_letter_pdf, staging_dir),
                    "role": "generated",
                    "pages": cover_letter_pages,
                },
                {
                    **_file_record(final_pdf, staging_dir),
                    "role": "generated",
                    "pages": final_page_count,
                },
                *[
                    {
                        **_file_record(path, staging_dir),
                        "role": "specification_sheet",
                        "pages": specsheet_page_counts[path.stem],
                    }
                    for path in specsheet_files
                ],
                *[
                    {
                        **_file_record(path, staging_dir),
                        "role": "supporting_input",
                    }
                    for path in support_files.values()
                ],
            ]
            manifest = {
                "manifest_version": 1,
                "run_id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "project_id": data.project.id,
                "manifest_file": "manifest.json",
                "inputs": input_records,
                "source_pdf_pages": source_proposal_pages,
                "artifacts": artifacts,
            }

            manifest_path = staging_dir / "manifest.json"
            temporary_manifest = staging_dir / "manifest.tmp.json"
            with temporary_manifest.open("w", encoding="utf-8", newline="\n") as file:
                json.dump(manifest, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_manifest, manifest_path)

            os.replace(staging_dir, package_dir)
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise

        data.files.proposal_package_folder = package_dir
        data.files.proposal_manifest = package_dir / "manifest.json"
        data.files.specsheets_folder = package_dir / "specsheets"
        data.files.cover_letter_pdf = package_dir / "cover_letter.pdf"
        data.files.final_proposal = package_dir / "final_proposal.pdf"
        return data.files.final_proposal

    @staticmethod
    def _parse_page_limit(value: Any, specsheet_name: str) -> int:
        """Parse a configured spec-sheet page limit as an integer."""
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError(
                f"Configured page count for {specsheet_name} must be an integer."
            )
        try:
            page_limit = int(value)
        except (ValueError, OverflowError) as exc:
            raise ValueError(
                f"Configured page count for {specsheet_name} must be an integer."
            ) from exc
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(
                f"Configured page count for {specsheet_name} must be an integer."
            )
        return page_limit

    def generate_email(self, data: DataManager, variables) -> None:
        """Create and display an Outlook draft with the final proposal attached."""
        data.update_from_pricing_spreadsheet()
        variables.update(data)

        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0: olMailItem
        mail.Subject = (
            f"Mid-State Solar - Proposal for {variables.resolve(r'{{SYSTEM_TYPE}}')}"
        )
        mail.To = variables.resolve(r"{{CLIENT_EMAIL}}")

        email_body = data.files.email_template.read_text(encoding="utf-8")
        for placeholder, replacement in variables.get_all().items():
            email_body = email_body.replace(str(placeholder), str(replacement))

        mail.HtmlBody = email_body
        system_type = (
            "PV"
            if data.system.type == 0
            else "ESS"
            if data.system.type == 1
            else "PV ESS"
        )
        attachment_name = (
            f"{datetime.now().strftime('%y_%m%d')} "
            f"{data.client.last_name}, {data.client.first_name} "
            f"{system_type} Proposal.pdf"
        )
        mail.Attachments.Add(str(data.files.final_proposal), 1, 0, attachment_name)
        mail.Display(False)

    @staticmethod
    def _replace_in_paragraph(paragraph, replacements: Mapping[str, Any]) -> None:
        """Replace paragraph placeholders across runs without losing formatting."""
        runs = paragraph.runs
        if not runs:
            return

        full_text = "".join(run.text for run in runs)
        if not full_text:
            return

        # Longest keys first, so a key that's a prefix of another (e.g. {{NAME}}
        # vs {{NAME_FULL}}) can't accidentally swallow part of the longer one.
        keys = sorted((str(k) for k in replacements if str(k)), key=len, reverse=True)
        if not keys:
            return
        pattern = re.compile("|".join(re.escape(k) for k in keys))

        matches = list(pattern.finditer(full_text))
        if not matches:
            return  # nothing to do, don't touch run formatting

        # Offset of each run within the concatenated full_text.
        run_spans = []
        pos = 0
        for run in runs:
            run_spans.append((pos, pos + len(run.text)))
            pos += len(run.text)

        # Flatten full_text into segments: unchanged text and matched placeholders.
        segments: list[tuple[int, int, bool, str | None]] = []
        cursor = 0
        for m in matches:
            if m.start() > cursor:
                segments.append((cursor, m.start(), False, None))
            segments.append((m.start(), m.end(), True, str(replacements[m.group(0)])))
            cursor = m.end()
        if cursor < len(full_text):
            segments.append((cursor, len(full_text), False, None))

        # Rebuild each run from whichever segments overlap its original span.
        for run, (rs, re_) in zip(runs, run_spans):
            if rs == re_:
                continue  # empty run

            pieces: list[str] = []
            for seg_start, seg_end, is_match, replacement in segments:
                if seg_end <= rs or seg_start >= re_:
                    continue  # segment doesn't touch this run

                if not is_match:
                    pieces.append(full_text[max(seg_start, rs) : min(seg_end, re_)])
                else:
                    # Emit the replacement only in the run that contains the
                    # *start* of the match, so a placeholder spanning several
                    # runs doesn't get duplicated.
                    assert replacement is not None
                    if rs <= seg_start < re_:
                        pieces.append(replacement)

            run.text = "".join(pieces)

    @staticmethod
    def get_cell_value(data: DataManager, sheet_name: str, cell_ref: str) -> Any:
        """Read a workbook cell, returning zero if the workbook or cell is unavailable."""
        if data.files.pricing_spreadsheet.exists():
            try:
                wb = load_workbook(
                    data.files.pricing_spreadsheet, data_only=True, read_only=True
                )
                if sheet_name in wb.sheetnames:
                    sheet = wb[sheet_name]
                    cell = sheet[cell_ref]
                    wb.close()
                    return cell.value
            except Exception as e:
                print(f"Error reading cell {cell_ref} from sheet {sheet_name}: {e}")
                return 0
        return 0

    def copy_to_fileserver(self, data: DataManager, settings: SettingsManager) -> Path:
        """Copy proposal files to the client bids folder using customer-facing names."""
        if not settings.files.bids_folder:
            raise ValueError("FILESERVER_BIDS_FOLDER environment variable is not set.")

        destination_folder = (
            Path(settings.files.bids_folder)
            / f"{data.client.last_name}, {data.client.first_name}"
        )
        destination_folder.mkdir(parents=True, exist_ok=True)
        package_dir = Path(data.files.proposal_package_folder)
        if not package_dir.is_dir() or not (package_dir / "manifest.json").is_file():
            raise ValueError(
                "A published proposal package is required before file-server copy."
            )

        system_type = (
            "PV"
            if data.system.type == 0
            else "ESS"
            if data.system.type == 1
            else "PV ESS"
        )
        dated_name = (
            f"{datetime.now().strftime('%y_%m%d')} "
            f"{data.client.last_name}, {data.client.first_name}"
        )
        file_names = {
            "final_proposal.pdf": f"{dated_name} {system_type} Proposal.pdf",
            "supporting/cover_letter_docx.docx": (
                f"PV ESS Proposal - {data.client.last_name}, "
                f"{data.client.first_name}.docx"
            ),
            "supporting/solargraf_proposal_pdf.pdf": (
                f"Proposal for - {data.client.name}.pdf"
            ),
            "supporting/pricing_spreadsheet.xlsx": (
                f"{dated_name} {system_type} Bid.xlsx"
            ),
        }
        staging_dir = (
            destination_folder / f".fileserver-copy.{uuid.uuid4().hex}.tmp"
        )
        try:
            staging_dir.mkdir()
            manifest = json.loads(
                (package_dir / "manifest.json").read_text(encoding="utf-8")
            )
            for artifact in manifest["artifacts"]:
                source_relative_path = Path(artifact["path"])
                source = package_dir / source_relative_path
                source_key = source_relative_path.as_posix()
                destination_name = file_names.get(
                    source_key, source_relative_path.name
                )
                target = staging_dir / destination_name
                _copy_file_fsynced(source, target)
                artifact["path"] = destination_name

            with (staging_dir / "manifest.json").open(
                "w", encoding="utf-8", newline="\n"
            ) as file:
                json.dump(manifest, file, indent=2, sort_keys=True)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            shutil.copytree(
                data.files.images_folder,
                staging_dir / "images",
                copy_function=_copy_file_fsynced,
            )
            for staged_file in staging_dir.iterdir():
                if staged_file.is_file():
                    os.replace(staged_file, destination_folder / staged_file.name)
            shutil.copytree(
                staging_dir / "images",
                destination_folder / "images",
                dirs_exist_ok=True,
                copy_function=_copy_file_fsynced,
            )
        except Exception:
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            raise

        shutil.rmtree(staging_dir)
        return destination_folder
