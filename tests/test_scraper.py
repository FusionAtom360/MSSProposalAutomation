import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import scraper
from data import DataManager, ProposalPdfMetrics


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
