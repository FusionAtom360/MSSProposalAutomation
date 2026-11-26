import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import DataManager, ProposalPdfMetrics
from ui import App


def test_download_proposal_document_refreshes_templates_with_pdf_metrics(tmp_path):
    data = DataManager()
    data.files.solargraf_proposal = tmp_path / "solargraf_proposal.pdf"
    template_updates: list[DataManager] = []

    class Scraper:
        def get_proposal_document(self, project_data):
            project_data.proposal_pdf_metrics = ProposalPdfMetrics(
                system_size_kw=11.31,
                annual_production_kwh=15925.6,
                usage_percentage=116,
            )
            return project_data.files.solargraf_proposal

    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            data=data,
            scraper=Scraper(),
            templates=SimpleNamespace(update=template_updates.append),
        ),
    )

    result = App.download_proposal_document(app)

    assert result == f"Downloaded proposal document to {data.files.solargraf_proposal}."
    assert template_updates == [data]
    assert data.proposal_pdf_metrics is not None
    assert data.proposal_pdf_metrics.annual_production_kwh == 15925.6


def test_open_pricing_spreadsheet_opens_existing_file_without_regenerating(
    tmp_path, monkeypatch
):
    spreadsheet = tmp_path / "pricing_spreadsheet.xlsx"
    spreadsheet.touch()
    generated = []
    opened = []
    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            data=SimpleNamespace(
                files=SimpleNamespace(pricing_spreadsheet=spreadsheet)
            ),
            office=SimpleNamespace(
                complete_pricing_spreadsheet=lambda *args: generated.append(args)
            ),
        ),
    )
    monkeypatch.setattr("ui.os.startfile", opened.append)

    result = App.open_pricing_spreadsheet(app)

    assert result == f"Opened pricing spreadsheet {spreadsheet}."
    assert opened == [spreadsheet]
    assert generated == []


def test_open_proposal_document_downloads_when_file_is_missing(tmp_path):
    proposal = tmp_path / "solargraf_proposal.pdf"
    downloads = []
    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            data=SimpleNamespace(files=SimpleNamespace(solargraf_proposal=proposal)),
            download_proposal_document=lambda: (
                downloads.append(proposal)
                or f"Downloaded proposal document to {proposal}."
            ),
        ),
    )

    result = App.open_proposal_document(app)

    assert result == f"Downloaded proposal document to {proposal}."
    assert downloads == [proposal]


def test_open_cover_letter_generates_when_file_is_missing(tmp_path, monkeypatch):
    cover_letter = tmp_path / "cover_letter.docx"
    generated = []
    opened = []
    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            data=SimpleNamespace(files=SimpleNamespace(cover_letter_docx=cover_letter)),
            office=SimpleNamespace(
                complete_cover_letter=lambda *args: generated.append(args)
            ),
            templates=object(),
        ),
    )
    monkeypatch.setattr("ui.os.startfile", opened.append)

    result = App.open_cover_letter(app)

    assert result == f"Opened cover letter at {cover_letter}."
    assert len(generated) == 1
    assert opened == [cover_letter]


def test_generate_cover_letter_regenerates_existing_file(tmp_path, monkeypatch):
    cover_letter = tmp_path / "cover_letter.docx"
    cover_letter.touch()
    generated = []
    opened = []
    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            data=SimpleNamespace(files=SimpleNamespace(cover_letter_docx=cover_letter)),
            office=SimpleNamespace(
                complete_cover_letter=lambda *args: generated.append(args)
            ),
            templates=object(),
        ),
    )
    monkeypatch.setattr("ui.os.startfile", opened.append)

    result = App.generate_cover_letter(app)

    assert result == f"Regenerated and opened cover letter at {cover_letter}."
    assert len(generated) == 1
    assert opened == [cover_letter]


def test_document_button_refresh_shows_regenerate_action_only_for_existing_file(
    tmp_path,
):
    class Button:
        def __init__(self):
            self.options = {}
            self.visible = True

        def configure(self, **options):
            self.options.update(options)

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

    existing_path = tmp_path / "pricing_spreadsheet.xlsx"
    existing_path.touch()
    missing_path = tmp_path / "cover_letter.docx"
    existing_button = Button()
    existing_action = Button()
    missing_button = Button()
    missing_action = Button()
    app = cast(
        App,
        SimpleNamespace(
            _document_buttons={
                "pricing": {
                    "path": lambda: existing_path,
                    "button": existing_button,
                    "secondary_button": existing_action,
                    "open_label": "Pricing Spreadsheet",
                    "create_label": "Generate Pricing Spreadsheet",
                },
                "cover": {
                    "path": lambda: missing_path,
                    "button": missing_button,
                    "secondary_button": missing_action,
                    "open_label": "Cover Letter",
                    "create_label": "Generate Cover Letter",
                },
            }
        ),
    )

    App._refresh_document_buttons(app)

    assert existing_button.options["text"] == "Pricing Spreadsheet"
    assert existing_action.visible
    assert missing_button.options["text"] == "Generate Cover Letter"
    assert not missing_action.visible


def test_continue_local_project_uses_saved_data_without_rewriting_it(
    tmp_path, monkeypatch
):
    projects_folder = tmp_path / "projects"
    project_folder = projects_folder / "123"
    project_folder.mkdir(parents=True)
    data_path = project_folder / "data.json"
    payload = {
        "id": 123,
        "public_id": "local-api-id",
        "client_name": "Local Customer",
        "Materials": {},
    }
    original_data = json.dumps(payload, indent=4).encode("utf-8")
    data_path.write_bytes(original_data)

    data = DataManager()
    data.settings.files.projects_folder = projects_folder
    load_json = data.load_json

    def load_without_saving(payload, save_to_file=True):
        assert save_to_file is False
        load_json(payload, save_to_file=save_to_file)

    monkeypatch.setattr(data, "load_json", load_without_saving)
    template_updates: list[DataManager] = []
    selected_projects = {}

    def select_project(projects, *, title, confirm_text):
        selected_projects["projects"] = projects
        selected_projects["title"] = title
        selected_projects["confirm_text"] = confirm_text
        return projects[0]

    app = cast(
        App,
        SimpleNamespace(
            settings=SimpleNamespace(
                files=SimpleNamespace(projects_folder=projects_folder)
            ),
            data=data,
            templates=SimpleNamespace(update=template_updates.append),
            _select_project_dialog=select_project,
        ),
    )

    result = App.continue_local_project(app)

    assert result == "Continued project 123."
    assert data.project.id == 123
    assert selected_projects["projects"][0]["name"] == "Local Customer"
    assert selected_projects["title"] == "Select a local project"
    assert selected_projects["confirm_text"] == "Continue Project"
    assert template_updates == [data]
    assert data_path.read_bytes() == original_data


def test_finalize_creates_package_without_drafting_email_or_copying_to_bids(
    tmp_path, monkeypatch
):
    final_proposal = tmp_path / "final_proposal.pdf"
    manifest = tmp_path / "manifest.json"
    published_path = tmp_path / "published"
    calls = []

    class Office:
        def finalize_proposal(self, data, templates, scraper):
            calls.append("finalize")
            return final_proposal

        def generate_email(self, data, templates):
            calls.append("email")

        def copy_to_fileserver(self, data, settings):
            calls.append("bids")
            return published_path

    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            _run_post_generation_action=App._run_post_generation_action,
            office=Office(),
            data=SimpleNamespace(
                files=SimpleNamespace(
                    final_proposal=final_proposal,
                    proposal_manifest=manifest,
                ),
                project=SimpleNamespace(id=123),
            ),
            templates=object(),
            scraper=object(),
            settings=object(),
        ),
    )
    monkeypatch.setattr("ui.os.startfile", lambda path: None)

    result = App.finalize_proposal(app)

    assert calls == ["finalize"]
    assert f"Final proposal package created at {final_proposal}." in result
    assert f"Manifest: {manifest}." in result
    assert "Open proposal: complete" in result


def test_draft_customer_email_runs_as_a_separate_action():
    calls = []
    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            _run_post_generation_action=App._run_post_generation_action,
            office=SimpleNamespace(
                generate_email=lambda data, templates: calls.append("email")
            ),
            data=object(),
            templates=object(),
        ),
    )

    result = App.draft_customer_email(app)

    assert calls == ["email"]
    assert result == "Email draft: complete"


def test_copy_to_bids_folder_runs_as_a_separate_action():
    published_path = Path("published")
    calls = []

    def copy_to_fileserver(data, settings):
        calls.append("bids")
        return published_path

    app = cast(
        App,
        SimpleNamespace(
            _require_project=lambda: None,
            _run_post_generation_action=App._run_post_generation_action,
            office=SimpleNamespace(copy_to_fileserver=copy_to_fileserver),
            data=object(),
            settings=object(),
        ),
    )

    result = App.copy_to_bids_folder(app)

    assert calls == ["bids"]
    assert result == f"Bids folder copy: complete ({published_path})"


def test_finalize_and_send_runs_existing_actions_in_order():
    calls = []
    app = cast(
        App,
        SimpleNamespace(
            finalize_proposal=lambda: calls.append("finalize") or "finalize: complete",
            draft_customer_email=lambda: calls.append("email") or "email: complete",
            copy_to_bids_folder=lambda: calls.append("bids") or "bids: complete",
        ),
    )

    result = App.finalize_and_send(app)

    assert calls == ["finalize", "email", "bids"]
    assert result == "finalize: complete\nemail: complete\nbids: complete"
