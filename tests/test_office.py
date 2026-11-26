import hashlib
import json
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock, call

import pytest
from docx import Document
from openpyxl import Workbook
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import DataManager
from office import OfficeDocumentManager
from scraper import Scraper as AppScraper
from settings import SettingsManager


def test_finalize_validates_prerequisites_before_external_operations(monkeypatch):
    data = DataManager()
    convert = Mock()
    monkeypatch.setattr("office.docx2pdf.convert", convert)

    with pytest.raises(ValueError, match="project ID"):
        OfficeDocumentManager().finalize_proposal(
            data, object(), cast(AppScraper, object())
        )

    convert.assert_not_called()


def test_finalize_shows_actionable_error_when_word_quit_is_unavailable(
    tmp_path, monkeypatch
):
    documents = tmp_path / "documents"
    documents.mkdir()
    cover_letter = documents / "cover_letter.docx"
    Document().save(cover_letter)
    proposal_pdf = documents / "solargraf_proposal.pdf"
    _write_pdf(proposal_pdf, 1, 602)
    pricing_spreadsheet = documents / "pricing_spreadsheet.xlsx"
    pricing_spreadsheet.touch()
    settings = documents / "settings.xlsx"
    settings.touch()

    data = DataManager()
    data.files.documents_folder = documents
    data.files.cover_letter_docx = cover_letter
    data.files.solargraf_proposal = proposal_pdf
    data.files.pricing_spreadsheet = pricing_spreadsheet
    data.files.settings = settings
    monkeypatch.setattr(data, "validate_for_document_generation", lambda kind: None)
    monkeypatch.setattr(
        "office.docx2pdf.convert",
        Mock(side_effect=AttributeError("Word.Application.Quit")),
    )

    with pytest.raises(
        RuntimeError,
        match="Word.Application.Quit is unavailable.*proposal package was not published",
    ) as exc_info:
        OfficeDocumentManager().finalize_proposal(
            data, object(), cast(AppScraper, object())
        )

    assert isinstance(exc_info.value.__cause__, AttributeError)
    assert list((documents / ".proposal-staging").iterdir()) == []
    assert list((documents / "proposal_packages").iterdir()) == []


def test_generate_email_uses_customer_friendly_attachment_name(tmp_path, monkeypatch):
    email_template = tmp_path / "email.html"
    email_template.write_text("<p>Proposal</p>", encoding="utf-8")
    final_proposal = tmp_path / "proposal_packages" / "run-id" / "final_proposal.pdf"
    final_proposal.parent.mkdir(parents=True)
    final_proposal.write_bytes(b"%PDF-1.4 test")
    data = SimpleNamespace(
        update_from_pricing_spreadsheet=Mock(),
        client=SimpleNamespace(first_name="Ada", last_name="Lovelace"),
        system=SimpleNamespace(type=0),
        files=SimpleNamespace(
            email_template=email_template,
            final_proposal=final_proposal,
        ),
    )
    variables = Mock()
    variables.resolve.side_effect = {
        r"{{SYSTEM_TYPE}}": "PV",
        r"{{CLIENT_EMAIL}}": "ada@example.com",
    }.__getitem__
    variables.get_all.return_value = {}
    mail = Mock()
    mail.Attachments.Count = 1
    monkeypatch.setattr(
        "office.win32.Dispatch",
        lambda name: SimpleNamespace(CreateItem=lambda item_type: mail),
    )
    monkeypatch.setattr(
        "office.datetime", SimpleNamespace(now=lambda: datetime(2026, 1, 2))
    )

    result = OfficeDocumentManager().generate_email(cast(DataManager, data), variables)

    assert result == final_proposal
    assert mail.BodyFormat == 2
    mail.Attachments.Add.assert_called_once_with(
        str(final_proposal), 1, 1, "26_0102 Lovelace, Ada PV Proposal.pdf"
    )
    assert mail.Save.call_count == 2
    assert mail.mock_calls.index(call.Save()) < mail.mock_calls.index(
        call.Attachments.Add(
            str(final_proposal), 1, 1, "26_0102 Lovelace, Ada PV Proposal.pdf"
        )
    )
    mail.Display.assert_called_once_with(False)


def test_generate_email_fails_when_final_proposal_is_missing(tmp_path):
    data = SimpleNamespace(
        update_from_pricing_spreadsheet=Mock(),
        files=SimpleNamespace(
            final_proposal=tmp_path / "missing.pdf",
        ),
    )

    with pytest.raises(FileNotFoundError, match="Final proposal PDF is missing"):
        OfficeDocumentManager().generate_email(cast(DataManager, data), Mock())


def test_finalize_combines_and_trims_cover_proposal_and_spec_sheets(
    tmp_path, monkeypatch
):
    root = tmp_path
    documents = root / "documents"
    specsheets = documents / "specsheets"
    specsheets.mkdir(parents=True)
    _write_pdf(specsheets / "unrelated.pdf", 4, 699)

    settings_path = root / "settings.xlsx"
    workbook = Workbook()
    workbook.active.title = "Aliases"
    workbook.create_sheet("Variables")
    spec_sheets = workbook.create_sheet("Spec Sheets")
    spec_sheets.append(["model", "pages"])
    spec_sheets.append(["Acme 400", 1])
    spec_sheets.append(["Acme 8K", 2])
    workbook.create_sheet("Spreadsheet")
    workbook.save(settings_path)

    cover_template = root / "cover_letter.docx"
    Document().save(cover_template)
    cover_letter_docx = documents / "cover_letter.docx"
    Document().save(cover_letter_docx)

    proposal_pdf = documents / "solargraf_proposal.pdf"
    _write_pdf(proposal_pdf, 2, 602)
    pricing_spreadsheet = documents / "pricing_spreadsheet.xlsx"
    Workbook().save(pricing_spreadsheet)

    data = DataManager()
    data.project.id = 123
    data.project.api_id = "api-id"
    data.project.proposal_id = "proposal-id"
    data.project.financial_id = "financial-id"
    data.client.name = "Ada Lovelace"
    data.client.first_name = "Ada"
    data.client.last_name = "Lovelace"
    data.client.address.street = "1 Analytical Engine Way"
    data.client.address.city = "London"
    data.client.address.region_code = "CA"
    data.client.address.postal_code = "90210"
    data.utility.name = "Example Utility"
    data.system.type = 0
    data.system.pv_size = 8.4
    data.system.panel.manufacturer = "Acme Solar"
    data.system.panel.model = "Acme 400"
    data.system.panel.size = 400
    data.system.panel.count = 21
    data.system.panel.specsheet_url = "https://example.com/panel.pdf"
    data.system.inverter.manufacturer = "Acme Inverters"
    data.system.inverter.model = "Acme 8K"
    data.system.inverter.count = 1
    data.system.inverter.specsheet_url = "https://example.com/inverter.pdf"
    data.files.settings = settings_path
    data.files.documents_folder = documents
    data.files.cover_letter_template = cover_template
    data.files.cover_letter_docx = cover_letter_docx
    data.files.cover_letter_pdf = documents / "cover_letter.pdf"
    data.files.solargraf_proposal = proposal_pdf
    data.files.pricing_spreadsheet = pricing_spreadsheet
    data.files.specsheets_folder = specsheets
    data.files.final_proposal = documents / "final.pdf"

    class Variables:
        def resolve(self, name):
            return {
                "{{PANEL_MODEL}}": "Acme 400",
                "{{INVERTER_MODEL}}": "Acme 8K",
            }.get(name, name)

    class Scraper:
        def __init__(self):
            self.downloaded = []

        def download(self, url, output_dir):
            self.downloaded.append(url)
            output = output_dir / Path(url).name
            width = 603 if "panel" in url else 604
            pages = 2 if "panel" in url else 3
            _write_pdf(output, pages, width)
            return output

    scraper = Scraper()

    def convert_cover_letter(source, target):
        _write_pdf(Path(target), 1, 601)

    convert = Mock(side_effect=convert_cover_letter)
    monkeypatch.setattr("office.docx2pdf.convert", convert)

    result = OfficeDocumentManager().finalize_proposal(
        data, Variables(), cast(AppScraper, scraper)
    )

    assert result == data.files.final_proposal
    pages = PdfReader(str(result)).pages
    assert len(pages) == 6
    assert [float(page.mediabox.width) for page in pages[:3]] == [601, 602, 602]
    assert sorted(float(page.mediabox.width) for page in pages[3:]) == [603, 604, 604]
    assert scraper.downloaded == [
        "https://example.com/panel.pdf",
        "https://example.com/inverter.pdf",
    ]
    assert len(PdfReader(str(data.files.specsheets_folder / "panel.pdf")).pages) == 1
    assert len(PdfReader(str(data.files.specsheets_folder / "inverter.pdf")).pages) == 2
    assert not (data.files.specsheets_folder / "unrelated.pdf").exists()
    assert (specsheets / "unrelated.pdf").is_file()
    assert Path(data.files.proposal_manifest).is_file()
    assert result.parent.name == data.files.proposal_package_folder.name
    manifest = json.loads(data.files.proposal_manifest.read_text(encoding="utf-8"))
    assert manifest["run_id"] == result.parent.name
    assert (
        manifest["inputs"]["solargraf_proposal_pdf"]["snapshot_sha256"]
        == hashlib.sha256(proposal_pdf.read_bytes()).hexdigest()
    )
    final_record = next(
        artifact
        for artifact in manifest["artifacts"]
        if artifact["path"] == "final_proposal.pdf"
    )
    assert final_record["sha256"] == hashlib.sha256(result.read_bytes()).hexdigest()
    convert.assert_called_once()
    assert convert.call_args.args[0] != str(cover_letter_docx)
    assert Path(convert.call_args.args[1]).name == "cover_letter.converted.pdf"

    second_result = OfficeDocumentManager().finalize_proposal(
        data, Variables(), cast(AppScraper, scraper)
    )
    assert second_result != result
    assert second_result.parent.name != result.parent.name
    assert len(list((documents / "proposal_packages").iterdir())) == 2
    original_packages = {
        result: result.read_bytes(),
        second_result: second_result.read_bytes(),
    }
    packages_before_failure = sorted(
        path.name for path in (documents / "proposal_packages").iterdir()
    )

    convert.reset_mock()
    proposal_pdf.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="Invalid PDF"):
        OfficeDocumentManager().finalize_proposal(
            data, Variables(), cast(AppScraper, scraper)
        )
    convert.assert_not_called()
    _write_pdf(proposal_pdf, 2, 602)

    def fail_download(url, output_dir):
        raise RuntimeError("specification download failed")

    monkeypatch.setattr(scraper, "download", fail_download)
    with pytest.raises(RuntimeError, match="specification download failed"):
        OfficeDocumentManager().finalize_proposal(
            data, Variables(), cast(AppScraper, scraper)
        )

    assert all(
        path.read_bytes() == content for path, content in original_packages.items()
    )
    assert (
        sorted(path.name for path in (documents / "proposal_packages").iterdir())
        == packages_before_failure
    )
    assert not list((documents / ".proposal-staging").iterdir())

    images = root / "images"
    images.mkdir()
    (images / "site-photo.jpg").write_bytes(b"fixture image")
    data.files.images_folder = images
    settings = SimpleNamespace(files=SimpleNamespace(bids_folder=root / "bids"))
    fileserver_package = OfficeDocumentManager().copy_to_fileserver(
        data, cast(SettingsManager, settings)
    )
    assert fileserver_package == root / "bids" / "Lovelace, Ada"
    date_prefix = f"{datetime.now().strftime('%y_%m%d')} Lovelace, Ada"
    expected_names = {
        f"{date_prefix} PV Proposal.pdf",
        f"{date_prefix} PV Bid.xlsx",
        "PV ESS Proposal - Lovelace, Ada.docx",
        "Proposal for - Ada Lovelace.pdf",
    }
    assert {
        path.name for path in fileserver_package.iterdir() if path.is_file()
    } == expected_names
    assert {path.name for path in fileserver_package.iterdir() if path.is_dir()} == {
        "images"
    }
    assert (
        fileserver_package / "images" / "site-photo.jpg"
    ).read_bytes() == b"fixture image"
    assert (
        OfficeDocumentManager().copy_to_fileserver(
            data, cast(SettingsManager, settings)
        )
        == fileserver_package
    )


def _write_pdf(path, pages, width):
    path.write_bytes(_pdf_bytes(pages, width))


def _pdf_bytes(pages, width):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=width, height=792)
    with BytesIO() as stream:
        writer.write(stream)
        return stream.getvalue()
