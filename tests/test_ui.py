import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data import DataManager, ProposalPdfMetrics
from ui import App


def test_download_proposal_document_refreshes_templates_with_pdf_metrics(tmp_path):
    data = DataManager()
    data.files.solargraf_proposal = tmp_path / "solargraf_proposal.pdf"
    template_updates = []

    class Scraper:
        def get_proposal_document(self, project_data):
            project_data.proposal_pdf_metrics = ProposalPdfMetrics(
                system_size_kw=11.31,
                annual_production_kwh=15925.6,
                usage_percentage=116,
            )
            return project_data.files.solargraf_proposal

    app = SimpleNamespace(
        _require_project=lambda: None,
        data=data,
        scraper=Scraper(),
        templates=SimpleNamespace(update=template_updates.append),
    )

    result = App.download_proposal_document(app)

    assert result == f"Downloaded proposal document to {data.files.solargraf_proposal}."
    assert template_updates == [data]
    assert data.proposal_pdf_metrics.annual_production_kwh == 15925.6


def test_continue_local_project_uses_saved_data_without_rewriting_it(tmp_path):
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

    data.load_json = load_without_saving
    template_updates = []
    selected_projects = {}

    def select_project(projects, *, title, confirm_text):
        selected_projects["projects"] = projects
        selected_projects["title"] = title
        selected_projects["confirm_text"] = confirm_text
        return projects[0]

    app = SimpleNamespace(
        settings=SimpleNamespace(
            files=SimpleNamespace(projects_folder=projects_folder)
        ),
        data=data,
        templates=SimpleNamespace(update=template_updates.append),
        _select_project_dialog=select_project,
    )

    result = App.continue_local_project(app)

    assert result == "Continued project 123."
    assert data.project.id == 123
    assert selected_projects["projects"][0]["name"] == "Local Customer"
    assert selected_projects["title"] == "Select a local project"
    assert selected_projects["confirm_text"] == "Continue Project"
    assert template_updates == [data]
    assert data_path.read_bytes() == original_data


def test_finalize_reports_email_failure_and_still_publishes_to_fileserver(
    tmp_path, monkeypatch
):
    final_proposal = tmp_path / "final_proposal.pdf"
    manifest = tmp_path / "manifest.json"
    published_path = tmp_path / "published"
    calls = []

    class Office:
        def finalize_proposal(self, data, templates, scraper):
            return final_proposal

        def generate_email(self, data, templates):
            raise RuntimeError("Outlook is unavailable")

        def copy_to_fileserver(self, data, settings):
            calls.append("fileserver")
            return published_path

    app = SimpleNamespace(
        _require_project=lambda: None,
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
    )
    monkeypatch.setattr("ui.os.startfile", lambda path: None)

    result = App.finalize_proposal(app)

    assert calls == ["fileserver"]
    assert "Email draft: FAILED (Outlook is unavailable)" in result
    assert f"File-server publication: complete ({published_path})" in result
