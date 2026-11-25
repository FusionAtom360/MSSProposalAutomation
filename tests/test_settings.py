import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from settings import APPLICATION_ROOT, SettingsManager


def test_default_application_paths_ignore_process_working_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BIDS_FOLDER", raising=False)

    files = SettingsManager().files

    assert files.projects_folder == APPLICATION_ROOT / "projects"
    assert files.templates_folder == APPLICATION_ROOT / "src" / "templates"
    assert files.settings == files.templates_folder / "settings.xlsx"
    assert files.bids_folder == APPLICATION_ROOT / "bids"


def test_relative_bids_folder_is_resolved_from_application_root(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BIDS_FOLDER", "shared-bids")

    assert SettingsManager().files.bids_folder == APPLICATION_ROOT / "shared-bids"


def test_absolute_bids_folder_override_is_preserved(tmp_path, monkeypatch):
    configured_folder = tmp_path / "custom-bids"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BIDS_FOLDER", str(configured_folder))

    assert SettingsManager().files.bids_folder == configured_folder.resolve()
