import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPOSITORY = "FusionAtom360/MSSProposalAutomation"
RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"


def install(root: Path):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    src = root / "src"
    helper_src = Path(__file__).resolve().parent / "src"
    if not (helper_src / "release_artifacts.py").is_file():
        raise RuntimeError(
            "Run install.py from a complete repository checkout, not a standalone copy."
        )

    answer = input(
        f"Install the latest signed MSS Proposal Automation release in {root}? (y/n): "
    )
    if answer.lower() != "y":
        return

    venv = root / ".venv"
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / "Scripts" / "python.exe"
    sigstore = venv / "Scripts" / "sigstore.exe"
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "-r",
            str(helper_src / "requirements-release.txt"),
        ],
        check=True,
    )
    sys.path.insert(0, str(venv / "Lib" / "site-packages"))
    sys.path.insert(0, str(helper_src))
    from release_artifacts import (
        download_asset,
        create_backup_path,
        extract_release_archive,
        preserve_local_files,
        release_assets,
        replace_directory,
        verify_release_artifact,
        version_from_release,
    )

    request = urllib.request.Request(
        RELEASE_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": REPOSITORY,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("The latest GitHub release is not a stable release")

    version = version_from_release(release)
    assets = release_assets(release)
    tag = release.get("tag_name")
    if not isinstance(tag, str):
        raise ValueError("Latest release has no tag")

    with tempfile.TemporaryDirectory(prefix=".mss-install-", dir=root) as temporary:
        temporary_root = Path(temporary)
        archive = temporary_root / assets["archive"]["name"]
        checksum = temporary_root / assets["checksum"]["name"]
        bundle = temporary_root / assets["bundle"]["name"]
        download_asset(assets["archive"], archive)
        download_asset(assets["checksum"], checksum)
        download_asset(assets["bundle"], bundle)

        verify_release_artifact(
            archive,
            checksum,
            bundle,
            sigstore,
            tag,
            version,
        )
        staged_root = temporary_root / "staged"
        staged_root.mkdir()
        extract_release_archive(archive, staged_root)
        staged_src = staged_root / "src"
        if not staged_src.is_dir():
            raise ValueError("Release archive does not contain application source")

        preserve_local_files(src, staged_src)

        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "-r",
                str(staged_src / "requirements.txt"),
                "-r",
                str(staged_src / "requirements-release.txt"),
            ],
            check=True,
        )
        backup = create_backup_path(root)
        replace_directory(src, staged_src, backup)
        if backup.exists():
            try:
                shutil.rmtree(backup)
            except OSError:
                print(f"Previous source backup retained at {backup}")

    environment_file = src / ".env"
    if not environment_file.exists():
        environment_file.write_text(
            "SOLARGRAF_EMAIL=\n"
            "SOLARGRAF_PASSWORD=\n"
            "LOAN_INTEREST_RATE=\n"
            "BIDS_FOLDER=\n",
            encoding="utf-8",
        )

    print(f"Installed verified version {version}.")
    subprocess.Popen([str(python), str(src / "main.py")], cwd=root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--install-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Application directory to install into (defaults to this checkout)",
    )
    install(parser.parse_args().install_dir)
