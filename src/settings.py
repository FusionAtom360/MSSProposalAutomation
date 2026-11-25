"""Application paths, credentials, and configurable workbook locations."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from openpyxl import load_workbook


APPLICATION_ROOT = Path(__file__).resolve().parent.parent


def _application_path(value: str) -> Path:
    """Resolve a configured path relative to the application root if needed."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = APPLICATION_ROOT / path
    return path.resolve()


def _default_bids_folder() -> Path:
    """Return the configured file-server path or its application default."""
    value = os.getenv("BIDS_FOLDER", "bids")
    return _application_path(value if value.strip() else "bids")


class SettingsManager():
    """Hold application authentication and file-location settings."""

    def __init__(self):
        """Initialize default authentication, file paths, and spec-sheet pages."""
        self.auth = self.Auth()
        self.files = self.Files()
        self.specsheet_pages = {}
        
    def set_auth_key(self, key: str):
        """Replace the stored SolarGraf authentication key."""
        self.auth.key = key
        
    @dataclass
    class Auth():
        """Authentication settings used for SolarGraf requests."""

        key: str = ""
    
    @dataclass
    class Files():
        """Filesystem locations for projects, templates, and bids."""

        projects_folder: Path = field(
            default_factory=lambda: APPLICATION_ROOT / "projects"
        )
        templates_folder: Path = field(
            default_factory=lambda: APPLICATION_ROOT / "src" / "templates"
        )
        bids_folder: Path = field(default_factory=_default_bids_folder)
        settings: Path = field(
            default_factory=lambda: APPLICATION_ROOT
            / "src"
            / "templates"
            / "settings.xlsx"
        )
