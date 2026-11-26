import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scraper
from data import DataManager, ProposalPdfMetrics
from settings import SettingsManager


class TextPage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


def test_extract_proposal_pdf_metrics_uses_precise_usage_breakdown_production(
    monkeypatch,
):
    pages = [
        TextPage(
            "Solar details System size11.31 kW DC "
            "Estimated first year production15,926 kWh Consumption offset116%"
        ),
        TextPage(
            "Usage breakdown Estimated first year consumption13,679.0 kWh "
            "Estimated first year production15,925.6 kWh"
        ),
    ]
    monkeypatch.setattr(
        scraper,
        "PdfReader",
        lambda _: SimpleNamespace(pages=pages),
    )

    metrics = scraper.extract_proposal_pdf_metrics(b"pdf")

    assert metrics == ProposalPdfMetrics(
        system_size_kw=11.31,
        annual_production_kwh=15925.6,
        usage_percentage=116,
    )


def test_extract_proposal_pdf_metrics_reports_missing_usage_breakdown(monkeypatch):
    pages = [
        TextPage(
            "Solar details System size11.31 kW DC "
            "Estimated first year production15,926 kWh Consumption offset116%"
        )
    ]
    monkeypatch.setattr(
        scraper,
        "PdfReader",
        lambda _: SimpleNamespace(pages=pages),
    )

    with pytest.raises(ValueError, match="usage breakdown"):
        scraper.extract_proposal_pdf_metrics(b"pdf")


def test_extract_proposal_pdf_metrics_preserves_decimal_offset(monkeypatch):
    pages = [
        TextPage(
            "Solar details System size11.31 kW DC "
            "Estimated first year production15,926 kWh Consumption offset116.5%"
        ),
        TextPage(
            "Usage breakdown Estimated first year consumption13,679.0 kWh "
            "Estimated first year production15,925.6 kWh"
        ),
    ]
    monkeypatch.setattr(
        scraper,
        "PdfReader",
        lambda _: SimpleNamespace(pages=pages),
    )

    metrics = scraper.extract_proposal_pdf_metrics(b"pdf")

    assert metrics.usage_percentage == 116.5


def test_refresh_auth_token_removes_quotes_from_env_token(monkeypatch):
    monkeypatch.setenv("REQUEST_AUTH_KEY", '"request-token"')
    instance = scraper.Scraper()
    settings = SettingsManager()
    get = Mock(
        side_effect=[
            SimpleNamespace(ok=False),
            SimpleNamespace(ok=True),
        ]
    )
    monkeypatch.setattr(instance.http, "get", get)

    instance._refresh_auth_token(settings)

    assert settings.auth.key == "request-token"
    assert get.call_args_list[1].kwargs["auth_key"] == "request-token"


def test_wait_for_auth_token_persists_unquoted_extension_token(
    monkeypatch,
):
    received = Event()
    received.set()
    server = SimpleNamespace(
        session=SimpleNamespace(token='"extension-token"', received=received),
        serve_forever=Mock(),
        shutdown=Mock(),
        server_close=Mock(),
    )
    thread = SimpleNamespace(start=Mock(), join=Mock())
    monkeypatch.delenv("REQUEST_AUTH_KEY", raising=False)
    monkeypatch.setattr(scraper, "TokenHTTPServer", lambda _: server)
    monkeypatch.setattr(scraper.threading, "Thread", lambda **_: thread)
    monkeypatch.setattr(scraper.webbrowser, "open", Mock())
    set_key = Mock()
    monkeypatch.setattr(scraper, "set_key", set_key)
    instance = scraper.Scraper()
    monkeypatch.setattr(instance.http, "get", Mock(return_value=SimpleNamespace(ok=False)))
    settings = SettingsManager()

    instance._wait_for_auth_token(settings)

    assert settings.auth.key == "extension-token"
    set_key.assert_called_once_with(
        str(Path(scraper.__file__).with_name(".env")),
        "REQUEST_AUTH_KEY",
        "extension-token",
    )


def test_get_proposal_document_saves_pdf_metrics_for_templates(tmp_path, monkeypatch):
    output_path = tmp_path / "solargraf_proposal.pdf"
    metrics = ProposalPdfMetrics(
        system_size_kw=11.31,
        annual_production_kwh=15925.6,
        usage_percentage=116,
    )

    class ValidDataManager(DataManager):
        def validate_for_document_generation(self, document_kind: str) -> None:
            assert document_kind == "proposal_download"

    data = ValidDataManager()
    data.project.api_id = "project-api-id"
    data.project.proposal_id = "proposal-id"
    data.project.financial_id = "financial-id"
    data.files.solargraf_proposal = output_path
    response = SimpleNamespace(ok=True, status_code=200, content=b"proposal-pdf")
    requested_urls = []
    instance = scraper.Scraper()

    def get_response(url, **_):
        requested_urls.append(url)
        return response

    monkeypatch.setattr(
        instance.http,
        "get",
        get_response,
    )
    monkeypatch.setattr(
        scraper,
        "extract_proposal_pdf_metrics",
        lambda _: metrics,
    )
    monkeypatch.setattr(scraper.os, "startfile", lambda _: None, raising=False)

    result = instance.get_proposal_document(data)

    assert result == output_path
    assert output_path.read_bytes() == b"proposal-pdf"
    assert data.proposal_pdf_metrics == metrics
    assert requested_urls == [
        "https://app.solargraf.com/financial/pdf/"
        "project-api-id/proposal-id/financial-id.pdf?lang=en"
    ]
