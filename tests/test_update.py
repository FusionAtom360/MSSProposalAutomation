import io
import json
import sys
from pathlib import Path

from packaging.version import Version

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from update import UpdateManager


def _release(version, *, prerelease):
    archive = f"mss-proposal-automation-{version}.zip"
    return {
        "body": f"Version: {version}\nArtifact: {archive}",
        "prerelease": prerelease,
        "assets": [
            {"name": archive},
            {"name": archive + ".sha256"},
            {"name": archive + ".sigstore.json"},
        ],
    }


def _manager(current_version):
    manager = UpdateManager.__new__(UpdateManager)
    manager.current = Version(current_version)
    return manager


def test_latest_release_prefers_stable_over_newer_prerelease(monkeypatch):
    stable = _release("0.5.1", prerelease=False)
    prerelease = _release("0.5.2.dev1", prerelease=True)
    releases = [stable, prerelease]
    monkeypatch.setattr(
        "update.urllib.request.urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(releases).encode()),
    )

    result = _manager("0.5.0").latest_release()

    assert result == (stable, Version("0.5.1"))


def test_latest_release_ignores_prerelease_when_no_stable_update_exists(
    monkeypatch,
):
    releases = [_release("0.5.1.dev1", prerelease=True)]
    monkeypatch.setattr(
        "update.urllib.request.urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(releases).encode()),
    )

    assert _manager("0.5.0").latest_release() is None
