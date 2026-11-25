import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from packaging.version import Version


REPOSITORY = "FusionAtom360/MSSProposalAutomation"
VERSION_TAG_PATTERN = re.compile(r"^v(\d+\.\d+\.\d+)$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def build_release(source_root: Path, output_dir: Path) -> tuple[str, str, Path]:
    ref = required_environment("GITHUB_REF")
    event = required_environment("GITHUB_EVENT_NAME")
    commit = required_environment("GITHUB_SHA")
    if not SHA_PATTERN.fullmatch(commit):
        raise ValueError("GITHUB_SHA must be a full lowercase commit SHA")
    if event != "push":
        raise ValueError("Only pushed commits can be published as releases")

    details_path = source_root / "src" / "details.json"
    details = json.loads(details_path.read_text(encoding="utf-8"))
    base_version = Version(details["version"])
    if str(base_version) != details["version"] or base_version.is_prerelease:
        raise ValueError("src/details.json must contain a stable PEP 440 version")

    tag_match = VERSION_TAG_PATTERN.fullmatch(ref.removeprefix("refs/tags/"))
    if ref.startswith("refs/tags/"):
        if not tag_match or tag_match.group(1) != str(base_version):
            raise ValueError("A version tag must match src/details.json")
        version = str(base_version)
        tag = f"v{version}"
    elif ref == "refs/heads/main":
        run_number = required_environment("GITHUB_RUN_NUMBER")
        run_attempt = required_environment("GITHUB_RUN_ATTEMPT")
        if not run_number.isdecimal() or not run_attempt.isdecimal():
            raise ValueError("GitHub run number and attempt must be numeric")
        major, minor, patch = (list(base_version.release) + [0, 0, 0])[:3]
        version = (
            f"{major}.{minor}.{patch + 1}.dev{run_number}"
            f"+run{run_attempt}.g{commit[:12]}"
        )
        tag = f"build-{run_number}-{run_attempt}-{commit[:12]}"
    else:
        raise ValueError("Releases may only be built from main or version tags")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"mss-proposal-automation-{version}.zip"
    package_details = dict(details)
    package_details["version"] = version
    metadata = {
        "repository": REPOSITORY,
        "version": version,
        "base_version": str(base_version),
        "commit": commit,
        "ref": ref,
        "event": event,
        "tag": tag,
    }

    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted((source_root / "src").rglob("*")):
            if not path.is_file() or path.name in {".env", ".gitignore"}:
                continue
            relative = path.relative_to(source_root).as_posix()
            if (
                "logs" in path.parts
                or "__pycache__" in path.parts
                or path.suffix == ".pyc"
            ):
                continue
            if relative == "src/details.json":
                archive.writestr(
                    relative,
                    json.dumps(package_details, indent=4) + "\n",
                )
            else:
                archive.write(path, relative)
        archive.writestr(
            "release.json",
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        )

    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = Path(str(archive_path) + ".sha256")
    checksum_path.write_text(
        f"{digest}  {archive_path.name}\n",
        encoding="ascii",
    )
    return version, tag, archive_path


def required_environment(name: str) -> str:
    import os

    value = os.environ.get(name)
    if not value:
        raise ValueError(f"{name} is required")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    version, tag, archive = build_release(args.source_root, args.output_dir)
    print(f"version={version}")
    print(f"tag={tag}")
    print(f"archive={archive.resolve()}")


if __name__ == "__main__":
    main()
