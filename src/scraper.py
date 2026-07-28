import json
import os
from pathlib import Path
from dotenv import load_dotenv
import re
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

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

    def get_project_data(self, data: DataManager) -> dict:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel=self.browser_channel, headless=self.headless)
            context = browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            if data.project.id and data.project.api_id:
                page.goto(
                    f"https://app.solargraf.com/projects/{data.project.id}",
                    wait_until="domcontentloaded",
                )
                self._login_if_possible(page, "Overview")
                preview_public_pattern = re.compile(
                    rf"^https://api\.solargraf\.com/projects/public/{re.escape(str(data.project.api_id))}(?:[/?#].*)?$"
                )
                with page.expect_response(
                    lambda response: preview_public_pattern.match(response.url),
                    timeout=120000,
                ) as preview_response_info:
                    page.goto(f"https://app.solargraf.com/preview/{data.project.api_id}", wait_until="domcontentloaded")

                preview_payload = preview_response_info.value.json()
                return preview_payload
            
            else:
                page.goto("https://app.solargraf.com/projects", wait_until="domcontentloaded")
                self._login_if_possible(page, "Projects")

                with page.expect_response(TARGET_PROJECT_RESPONSE) as initial_response_info:
                    page.wait_for_timeout(1000)

                initial_payload = initial_response_info.value.json()
                data.set_api_id(initial_payload.get("public_id"))
                if not data.project.api_id:
                    raise RuntimeError("Project response did not include public_id")

                preview_public_pattern = re.compile(
                    rf"^https://api\.solargraf\.com/projects/public/{re.escape(str(data.project.api_id))}(?:[/?#].*)?$"
                )
                with page.expect_response(
                    lambda response: preview_public_pattern.match(response.url),
                    timeout=120000,
                ) as preview_response_info:
                    page.goto(f"https://app.solargraf.com/preview/{data.project.api_id}", wait_until="domcontentloaded")

                preview_payload = preview_response_info.value.json()
                return preview_payload
    
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

    def get_spec_sheet(self, url: str, output_dir: str | Path | None = None):
        if not isinstance(url, str):
            raise ValueError(f"Spec sheet URL must be a string, got {type(url).__name__}")

        normalized_url = url.strip()
        if not normalized_url or not self._is_http_url(normalized_url):
            raise ValueError(f"Spec sheet URL must be a valid HTTP(S) URL, got: {url!r}")

        with sync_playwright() as p:
            request_context = p.request.new_context()

            response = request_context.get(normalized_url)
            if not response.ok:
                raise RuntimeError(
                    "Failed to download spec sheet PDF: "
                    f"HTTP {response.status}"
                )

            target_dir = Path(output_dir) if output_dir else Path("specsheets")
            output_path = target_dir / f"{self.spec_sheet_counter}.pdf"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(response.body())

            self.spec_sheet_counter += 1

            request_context.dispose()
            return output_path
