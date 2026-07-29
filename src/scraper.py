import re
from urllib.parse import urlparse
import os
from pathlib import Path
from dotenv import load_dotenv, set_key
import json
import dotenv
import requests
from settings import SettingsManager
from token_receiver import TokenReceiver
from http.server import HTTPServer
import threading

from playwright.sync_api import sync_playwright
import webbrowser

from data import DataManager

load_dotenv()


TARGET_PROJECT_PAGE = re.compile(r"^https://app\.solargraf\.com/projects/[^/?#]+$")
TARGET_PROJECT_RESPONSE = re.compile(r"^https://api\.solargraf\.com/projects/[^/?#]+$")


class Scraper:
    def __init__(self, headless: bool = False, browser_channel: str = "chrome") -> None:
        self.headless = headless
        self.browser_channel = browser_channel
        self.spec_sheet_counter = 0
        
    def _dismiss_cookie_banner(self, page) -> None:
        reject_button = page.locator("#onetrust-reject-all-handler")
        if reject_button.count():
            try:
                reject_button.click(timeout=3000)
            except Exception:
                pass

    def _login_if_possible(self, page, check_text) -> None:
        email = os.getenv("SOLARGRAF_EMAIL")
        password = os.getenv("SOLARGRAF_PASSWORD")

        if not email or not password:
            raise RuntimeError("SOLARGRAF_EMAIL and SOLARGRAF_PASSWORD must be set before signing in")

        page.locator("#login_credentials_textfield_email").fill(email)
        page.locator("#login_credentials_textfield_password").fill(password)
        page.locator("#login_form_button_signin").click()
        page.wait_for_load_state("load")
        page.get_by_text(check_text).first.wait_for(state="visible")

    def _extract_project_id(self, payload: dict) -> str:
        project_id = payload.get("project_id") or payload.get("id") or payload.get("_id")
        if not project_id:
            raise RuntimeError("Project response did not include a project_id, id, or _id field")

        return str(project_id)

    def _wait_for_project_page(self, page) -> None:
        while not TARGET_PROJECT_PAGE.match(page.url):
            page.wait_for_timeout(1000)

    def get_project_data(self, data: DataManager, settings: SettingsManager) -> dict:
        self._refresh_auth_token(settings)
        
        response = requests.get(
            f"https://api.solargraf.com/public/project/{data.project.api_id}",
            headers={
                "authorization": f"Bearer {settings.auth.key}",
            },
            timeout=30
        )
        if not response.ok:
            raise RuntimeError(
                "Failed to retrieve project data: "
                f"HTTP {response.status_code}"
            )
        
        return response.json()
    
    def get_proposal_document(self, data: DataManager) -> Path:
        with sync_playwright() as p:
            request_context = p.request.new_context()

            base_url = "https://app.solargraf.com"
            pdf_path = (
                f"/financial/pdf/"
                f"{data.project.api_id}/"
                f"{data.project.proposal_id}/"
                f"{data.project.financial_id}.pdf"
            )
            download_url = (
                f"{base_url}"
                f"{pdf_path}"
                f"?lang=en"
            )
            response = request_context.get(download_url)
            if not response.ok:
                raise RuntimeError(
                    "Failed to download proposal PDF: "
                    f"HTTP {response.status}"
                )

            data.files.solargraf_proposal.write_bytes(response.body())
            os.startfile(data.files.solargraf_proposal)

            request_context.dispose()
            return data.files.solargraf_proposal
    
    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def download(self, url: str, output_dir: Path):
        if not isinstance(url, str):
            raise ValueError(f"URL must be a string, got {type(url).__name__}")

        normalized_url = url.strip()
        if not normalized_url or not self._is_http_url(normalized_url):
            raise ValueError(f"URL must be a valid HTTP(S) URL, got: {url!r}")

        with sync_playwright() as p:
            request_context = p.request.new_context()

            response = request_context.get(normalized_url)
            if not response.ok:
                raise RuntimeError(
                    "Failed to download: "
                    f"HTTP {response.status}"
                )

            target_dir = Path(output_dir) if output_dir else Path("downloads")
            output_path = target_dir / f"{self.spec_sheet_counter}.pdf"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.body())

            self.spec_sheet_counter += 1

            request_context.dispose()
            return output_path

    def get_spec_sheet(self, url: str, output_dir: Path):
        url = url.strip()
        if not url or not self._is_http_url(url):
            raise ValueError(f"Spec sheet URL must be a valid HTTP(S) URL, got: {url!r}")

        response = requests.get(url, timeout=30)
        if not response.ok:
            raise RuntimeError(
                "Failed to download spec sheet PDF: "
                f"HTTP {response.status_code}"
            )

        output_path = output_dir / f"{self.spec_sheet_counter}.pdf"
        output_path.write_bytes(response.content)

        self.spec_sheet_counter += 1

        return output_path
    
    def get_projects(self, settings: SettingsManager) -> list[DataManager]:
        self._refresh_auth_token(settings)

        response = requests.get(
            "https://api.solargraf.com/companies/27792/projects?sort=last_modified_at&desc=true&limit=20",
            headers={
                "authorization": f"Bearer {settings.auth.key}",
            },
            timeout=30
        )
        if not response.ok:
            raise RuntimeError(
                "Failed to retrieve projects: "
                f"HTTP {response.status_code}"
            )

        project_data = []
        for project in response.json()["data"]:
            data = DataManager()
            data.load_json(project, False)
            data.set_api_id(project.get("public_id"))
            project_data.append(data)

        return project_data

    def _refresh_auth_token(self, settings: SettingsManager) -> None:
        if requests.get("https://api.solargraf.com/companies/27792/projects", headers={"authorization": f"Bearer {settings.auth.key}"}, timeout=30).ok:
            return
        if requests.get("https://api.solargraf.com/companies/27792/projects", headers={"authorization": f"Bearer {os.getenv("REQUEST_AUTH_KEY")}"}, timeout=30).ok:
            settings.set_auth_key(str(os.getenv("REQUEST_AUTH_KEY")))
            return
        server = HTTPServer(
            ("127.0.0.1", 8765),
            TokenReceiver
        )
        thread = threading.Thread(
            target=server.serve_forever,
            daemon=True
        )
        thread.start()
        print("Waiting for Solargraf authentication...")
        webbrowser.open("https://app.solargraf.com")
        timeout = 300
        for _ in range(timeout):
            if TokenReceiver.token:
                settings.set_auth_key(TokenReceiver.token)
                dotenv.set_key("src/.env", "REQUEST_AUTH_KEY", TokenReceiver.token)
                server.shutdown()
                return
            import time
            time.sleep(1)

        server.shutdown()

        raise TimeoutError(
            "Timed out waiting for Solargraf token."
        ) 
