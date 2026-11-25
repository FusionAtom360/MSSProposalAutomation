import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from package_release import build_release
from release_artifacts import (
    REPOSITORY,
    WORKFLOW_NAME,
    extract_release_archive,
    preserve_local_files,
    replace_directory,
    verify_release_artifact,
)


def test_signed_metadata_and_workflow_identity_are_required(tmp_path, monkeypatch):
    archive, checksum = _make_archive(tmp_path)
    bundle = tmp_path / "release.sigstore.json"
    bundle.write_text("bundle", encoding="utf-8")
    verifier = tmp_path / "sigstore.exe"
    run = Mock()
    monkeypatch.setattr("release_artifacts.subprocess.run", run)

    manifest = verify_release_artifact(
        archive,
        checksum,
        bundle,
        verifier,
        "build-7-1-abcdef123456",
        Version("0.4.1.dev7+run1.gabcdef123456"),
    )

    assert manifest["commit"] == "a" * 40
    run.assert_called_once()
    command = run.call_args.args[0]
    assert WORKFLOW_NAME in command
    assert REPOSITORY in command
    assert "refs/heads/main" in command
    assert (
        f"https://github.com/{REPOSITORY}/.github/workflows/release.yml"
        "@refs/heads/main"
    ) in command


def test_checksum_mismatch_rejects_artifact_before_signature_check(
    tmp_path, monkeypatch
):
    archive, checksum = _make_archive(tmp_path)
    checksum.write_text("0" * 64, encoding="ascii")
    bundle = tmp_path / "bundle"
    bundle.write_text("bundle", encoding="utf-8")
    run = Mock()
    monkeypatch.setattr("release_artifacts.subprocess.run", run)

    with pytest.raises(ValueError, match="checksum"):
        verify_release_artifact(
            archive,
            checksum,
            bundle,
            tmp_path / "sigstore.exe",
            "build-7-1-abcdef123456",
            Version("0.4.1.dev7+run1.gabcdef123456"),
        )

    run.assert_not_called()


def test_invalid_signature_is_rejected(tmp_path, monkeypatch):
    archive, checksum = _make_archive(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.write_text("bundle", encoding="utf-8")
    run = Mock(
        side_effect=subprocess.CalledProcessError(
            1,
            ["sigstore"],
            stderr="signature did not match",
        )
    )
    monkeypatch.setattr("release_artifacts.subprocess.run", run)

    with pytest.raises(ValueError, match="signature did not match"):
        verify_release_artifact(
            archive,
            checksum,
            bundle,
            tmp_path / "sigstore.exe",
            "build-7-1-abcdef123456",
            Version("0.4.1.dev7+run1.gabcdef123456"),
        )


def test_archive_path_traversal_is_rejected(tmp_path):
    archive = tmp_path / "unsafe.zip"
    manifest = {
        "repository": REPOSITORY,
        "version": "0.4.1.dev7+run1.gabcdef123456",
        "commit": "a" * 40,
        "ref": "refs/heads/main",
        "event": "push",
        "tag": "build-7-1-abcdef123456",
    }
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("release.json", json.dumps(manifest))
        package.writestr(
            "src/details.json", json.dumps({"version": manifest["version"]})
        )
        package.writestr("src/../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="unsafe path"):
        extract_release_archive(archive, tmp_path / "output")


def test_failed_directory_swap_restores_previous_application(
    tmp_path, monkeypatch
):
    current = tmp_path / "src"
    staged = tmp_path / "staged"
    backup = tmp_path / "backup"
    current.mkdir()
    staged.mkdir()
    (current / "app.py").write_text("old", encoding="utf-8")
    (staged / "app.py").write_text("new", encoding="utf-8")

    real_replace = os.replace
    calls = 0

    def fail_staged_swap(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("simulated locked source")
        real_replace(source, destination)

    monkeypatch.setattr("release_artifacts.logger", Mock())
    monkeypatch.setattr("release_artifacts.os.replace", fail_staged_swap)

    with pytest.raises(PermissionError, match="locked"):
        replace_directory(current, staged, backup)

    assert (current / "app.py").read_text(encoding="utf-8") == "old"


def test_release_can_be_installed_into_empty_directory(tmp_path):
    current = tmp_path / "src"
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "app.py").write_text("new", encoding="utf-8")

    replace_directory(current, staged, tmp_path / "backup")

    assert (current / "app.py").read_text(encoding="utf-8") == "new"


def test_failed_rollback_retains_previous_source_backup(tmp_path, monkeypatch):
    current = tmp_path / "src"
    staged = tmp_path / "staged"
    backup = tmp_path / ".mss-src-backup"
    current.mkdir()
    staged.mkdir()
    (current / "app.py").write_text("old", encoding="utf-8")

    real_replace = os.replace
    calls = 0

    def fail_swap_and_rollback(source, destination):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise PermissionError("simulated locked directory")
        real_replace(source, destination)

    monkeypatch.setattr("release_artifacts.logger", Mock())
    monkeypatch.setattr("release_artifacts.os.replace", fail_swap_and_rollback)

    with pytest.raises(RuntimeError, match="rollback failed"):
        replace_directory(current, staged, backup)

    assert not current.exists()
    assert (backup / "app.py").read_text(encoding="utf-8") == "old"


def test_local_environment_and_logs_are_preserved(tmp_path):
    current = tmp_path / "current"
    staged = tmp_path / "staged"
    current.mkdir()
    staged.mkdir()
    (current / ".env").write_text("TOKEN=local\n", encoding="utf-8")
    (current / "logs").mkdir()
    (current / "logs" / "app.log").write_text("old log\n", encoding="utf-8")

    preserve_local_files(current, staged)

    assert (staged / ".env").read_text(encoding="utf-8") == "TOKEN=local\n"
    assert (staged / "logs" / "app.log").read_text(encoding="utf-8") == "old log\n"


def test_existing_templates_are_preserved_without_merging_release_defaults(tmp_path):
    current = tmp_path / "current"
    staged = tmp_path / "staged"
    current_templates = current / "templates"
    staged_templates = staged / "templates"
    current_templates.mkdir(parents=True)
    staged_templates.mkdir(parents=True)
    (current_templates / "settings.xlsx").write_text("user-edited", encoding="utf-8")
    (current_templates / "custom-template.docx").write_text(
        "user-added", encoding="utf-8"
    )
    (staged_templates / "settings.xlsx").write_text(
        "release-default", encoding="utf-8"
    )
    (staged_templates / "new-default.xlsx").write_text(
        "release-added", encoding="utf-8"
    )

    preserve_local_files(current, staged)

    assert (staged_templates / "settings.xlsx").read_text(encoding="utf-8") == "user-edited"
    assert (staged_templates / "custom-template.docx").read_text(
        encoding="utf-8"
    ) == "user-added"
    assert not (staged_templates / "new-default.xlsx").exists()


def test_custom_field_schema_is_preserved_during_update(tmp_path):
    current = tmp_path / "current"
    staged = tmp_path / "staged"
    current.mkdir()
    staged.mkdir()
    installed_schema = current / "field_schema.json"
    installed_schema.write_text('{"enforcement": "advisory"}', encoding="utf-8")
    (staged / "field_schema.json").write_text(
        '{"enforcement": "enforce"}', encoding="utf-8"
    )

    preserve_local_files(current, staged)

    assert (staged / "field_schema.json").read_text(encoding="utf-8") == (
        '{"enforcement": "advisory"}'
    )


def test_main_build_has_commit_specific_version_and_excludes_local_data(
    tmp_path, monkeypatch
):
    src = tmp_path / "src"
    (src / "logs").mkdir(parents=True)
    (src / "details.json").write_text(
        json.dumps({"version": "0.4.0", "changelog": []}),
        encoding="utf-8",
    )
    (src / "main.py").write_text("print('app')\n", encoding="utf-8")
    (src / ".env").write_text("SECRET=value\n", encoding="utf-8")
    (src / "logs" / "app.log").write_text("log\n", encoding="utf-8")
    commit = "b" * 40

    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_SHA", commit)
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "17")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")

    version, tag, archive = build_release(tmp_path, tmp_path / "dist")

    assert version == "0.4.1.dev17+run2.g" + commit[:12]
    assert Version(version) > Version("0.4.0")
    assert Version(version) < Version("0.4.1")
    assert tag == "build-17-2-" + commit[:12]
    assert archive.is_file()
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "release.json" in names
        assert "src/main.py" in names
        assert "src/.env" not in names
        assert "src/logs/app.log" not in names
        packaged_details = json.loads(package.read("src/details.json"))
        assert packaged_details["version"] == version

    expected_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert (
        Path(str(archive) + ".sha256")
        .read_text(encoding="ascii")
        .startswith(expected_hash)
    )


def _make_archive(root: Path) -> tuple[Path, Path]:
    archive = root / "release.zip"
    manifest = {
        "repository": REPOSITORY,
        "version": "0.4.1.dev7+run1.gabcdef123456",
        "commit": "a" * 40,
        "ref": "refs/heads/main",
        "event": "push",
        "tag": "build-7-1-abcdef123456",
    }
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("release.json", json.dumps(manifest))
        package.writestr(
            "src/details.json", json.dumps({"version": manifest["version"]})
        )
        package.writestr("src/main.py", "print('signed')\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = root / "release.zip.sha256"
    checksum.write_text(f"{digest}  release.zip\n", encoding="ascii")
    return archive, checksum
