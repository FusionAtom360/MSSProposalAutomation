from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from packaging.version import InvalidVersion, Version


REPOSITORY = "FusionAtom360/MSSProposalAutomation"
WORKFLOW_NAME = "Publish signed releases"
WORKFLOW_PATH = ".github/workflows/release.yml"
MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
MAX_CHECKSUM_SIZE = 4096
MAX_BUNDLE_SIZE = 10 * 1024 * 1024
MAX_UNPACKED_SIZE = 200 * 1024 * 1024
MAX_ARCHIVE_FILES = 1000
MAX_MANIFEST_SIZE = 16 * 1024
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
logger = logging.getLogger("mss_proposal_automation.release")


def version_from_release(release: dict[str, Any]) -> Version:
    body = release.get("body", "")
    match = re.search(r"^Version: ([^\s]+)$", body, re.MULTILINE)
    if not match:
        raise ValueError("Release is missing its version metadata")
    try:
        return Version(match.group(1))
    except InvalidVersion as exc:
        raise ValueError("Release contains an invalid version") from exc


def release_assets(release: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise ValueError("Release assets are missing")

    by_name = {
        asset.get("name"): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    archive_name = release.get("body", "")
    match = re.search(r"^Artifact: ([^\s]+\.zip)$", archive_name, re.MULTILINE)
    if not match:
        raise ValueError("Release is missing its artifact name")
    name = match.group(1)
    required = {
        "archive": name,
        "checksum": name + ".sha256",
        "bundle": name + ".sigstore.json",
    }
    try:
        return {key: by_name[value] for key, value in required.items()}
    except KeyError as exc:
        raise ValueError(f"Release is missing required asset: {exc.args[0]}") from exc


def download_asset(asset: dict[str, Any], destination: Path) -> None:
    url = asset.get("browser_download_url")
    expected_prefix = (
        f"https://github.com/{REPOSITORY}/releases/download/"
    )
    if not isinstance(url, str) or not url.startswith(expected_prefix):
        raise ValueError("Release asset URL is not from the expected repository")

    import urllib.request

    request = urllib.request.Request(
        url,
        headers={"Accept": "application/octet-stream", "User-Agent": REPOSITORY},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_ARCHIVE_SIZE:
            raise ValueError("Release asset exceeds the allowed size")

        total = 0
        with destination.open("wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_SIZE:
                    raise ValueError("Release asset exceeds the allowed size")
                output.write(chunk)


def _read_manifest(archive: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(archive) as package:
            _validate_archive_entries(package)
            info = package.getinfo("release.json")
            if info.file_size > MAX_MANIFEST_SIZE:
                raise ValueError("Release manifest is too large")
            manifest = json.loads(package.read(info).decode("utf-8"))
    except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Release archive or manifest is invalid") from exc

    if not isinstance(manifest, dict):
        raise ValueError("Release manifest must be a JSON object")
    return manifest


def verify_release_artifact(
    archive: Path,
    checksum_file: Path,
    bundle: Path,
    verifier: Path,
    expected_tag: str,
    expected_version: Version,
) -> dict[str, Any]:
    if archive.stat().st_size > MAX_ARCHIVE_SIZE:
        raise ValueError("Release archive exceeds the allowed size")
    if checksum_file.stat().st_size > MAX_CHECKSUM_SIZE:
        raise ValueError("Release checksum file exceeds the allowed size")
    if bundle.stat().st_size > MAX_BUNDLE_SIZE:
        raise ValueError("Sigstore bundle exceeds the allowed size")

    checksum_fields = checksum_file.read_text(encoding="ascii").strip().split()
    if not checksum_fields or not re.fullmatch(r"[0-9a-f]{64}", checksum_fields[0]):
        raise ValueError("Release checksum file is invalid")
    actual_checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    if not hmac.compare_digest(checksum_fields[0], actual_checksum):
        raise ValueError("Release archive checksum does not match")

    manifest = _read_manifest(archive)
    version_text = manifest.get("version")
    try:
        manifest_version = Version(version_text)
    except (InvalidVersion, TypeError) as exc:
        raise ValueError("Release manifest has an invalid version") from exc

    commit = manifest.get("commit")
    reference = manifest.get("ref")
    event = manifest.get("event")
    tag = manifest.get("tag")
    if (
        manifest.get("repository") != REPOSITORY
        or not isinstance(version_text, str)
        or manifest_version != expected_version
        or tag != expected_tag
        or not isinstance(commit, str)
        or not COMMIT_PATTERN.fullmatch(commit)
        or event != "push"
    ):
        raise ValueError("Release manifest does not match the selected release")

    is_main_build = (
        reference == "refs/heads/main"
        and expected_tag.startswith("build-")
        and manifest_version.is_prerelease
    )
    is_version_tag = (
        isinstance(reference, str)
        and reference.startswith("refs/tags/v")
        and reference == f"refs/tags/{expected_tag}"
        and expected_tag == f"v{manifest_version}"
        and not manifest_version.is_prerelease
    )
    if not (is_main_build or is_version_tag):
        raise ValueError("Release ref or tag is not an allowed release source")

    with zipfile.ZipFile(archive) as package:
        details_info = package.getinfo("src/details.json")
        details = json.loads(package.read(details_info).decode("utf-8"))
    if not isinstance(details, dict) or details.get("version") != version_text:
        raise ValueError("Release version does not match the packaged application")

    command = [
        str(verifier),
        "verify",
        "github",
        "--bundle",
        str(bundle),
        "--cert-identity",
        f"https://github.com/{REPOSITORY}/{WORKFLOW_PATH}@{reference}",
        "--repository",
        REPOSITORY,
        "--name",
        WORKFLOW_NAME,
        "--ref",
        reference,
        "--sha",
        commit,
        "--trigger",
        event,
        str(archive),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as exc:
        verification_output = (exc.stderr or exc.stdout or "").strip()
        raise ValueError(
            "Sigstore verification failed"
            + (f": {verification_output}" if verification_output else "")
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Sigstore verification timed out") from exc
    logger.info(
        "Release signature verified version=%s commit=%s ref=%s",
        version_text,
        commit,
        reference,
    )
    return manifest


def preserve_local_files(current_src: Path, staged_src: Path) -> None:
    environment_file = current_src / ".env"
    if environment_file.is_file():
        shutil.copy2(environment_file, staged_src / ".env")

    logs_directory = current_src / "logs"
    if logs_directory.is_dir():
        shutil.copytree(logs_directory, staged_src / "logs", dirs_exist_ok=True)

    field_schema_file = current_src / "field_schema.json"
    if field_schema_file.is_file():
        shutil.copy2(field_schema_file, staged_src / "field_schema.json")

    templates_directory = current_src / "templates"
    if templates_directory.is_dir():
        staged_templates_directory = staged_src / "templates"
        if staged_templates_directory.exists():
            if staged_templates_directory.is_dir():
                shutil.rmtree(staged_templates_directory)
            else:
                staged_templates_directory.unlink()
        shutil.copytree(templates_directory, staged_templates_directory)


def create_backup_path(parent: Path) -> Path:
    backup = Path(
        tempfile.mkdtemp(prefix=".mss-src-backup-", dir=parent)
    )
    backup.rmdir()
    return backup


def extract_release_archive(archive: Path, destination: Path) -> dict[str, Any]:
    with zipfile.ZipFile(archive) as package:
        _validate_archive_entries(package)
        manifest = _read_manifest(archive)
        for info in package.infolist():
            path = PurePosixPath(info.filename)
            if info.is_dir():
                continue
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    return manifest


def replace_directory(current: Path, staged: Path, backup: Path) -> None:
    if not current.exists():
        os.replace(staged, current)
        return
    os.replace(current, backup)
    try:
        os.replace(staged, current)
    except OSError as swap_error:
        try:
            os.replace(backup, current)
        except OSError as rollback_error:
            logger.exception(
                "Application source swap and rollback both failed; "
                "source backup remains at %s",
                backup,
            )
            raise RuntimeError(
                f"Source swap failed ({swap_error}); rollback failed ({rollback_error})"
            ) from swap_error
        logger.error("Application source swap failed; previous source restored")
        raise


def _validate_archive_entries(package: zipfile.ZipFile) -> None:
    entries = package.infolist()
    if len(entries) > MAX_ARCHIVE_FILES:
        raise ValueError("Release archive contains too many files")

    total_size = 0
    seen: set[str] = set()
    for info in entries:
        name = info.filename
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (
            not name
            or "\\" in name
            or "\x00" in name
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or ":" in name
            or ".env" in path.parts
            or "logs" in path.parts
            or (name != "release.json" and not name.startswith("src/"))
            or name in seen
            or stat.S_ISLNK(mode)
        ):
            raise ValueError("Release archive contains an unsafe path")
        seen.add(name)
        total_size += info.file_size
        if total_size > MAX_UNPACKED_SIZE:
            raise ValueError("Release archive expands beyond the allowed size")

    if "release.json" not in seen or "src/details.json" not in seen:
        raise ValueError("Release archive is missing required files")
