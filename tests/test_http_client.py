import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from http_client import AuthenticatedHttpClient


def test_authenticated_client_applies_header_and_configured_timeout(monkeypatch):
    client = AuthenticatedHttpClient(timeout=17)
    response = object()
    get = Mock(return_value=response)
    monkeypatch.setattr(client.session, "get", get)

    assert client.get("https://example.com/resource", auth_key="token") is response

    get.assert_called_once_with(
        "https://example.com/resource",
        headers={"authorization": "Bearer token"},
        timeout=17,
    )


def test_request_log_redacts_sensitive_headers_but_keeps_context(monkeypatch):
    client = AuthenticatedHttpClient()
    get = Mock(return_value=object())
    logger = Mock()
    monkeypatch.setattr(client.session, "get", get)
    monkeypatch.setattr("http_client.logger", logger)

    client.get(
        "https://example.com/resource",
        auth_key="secret-token",
        headers={
            "Authorization": "stale-token",
            "Cookie": "session=secret",
            "Proxy-Authorization": "proxy-secret",
            "Set-Cookie": "cookie-secret",
            "X-API-Key": "api-secret",
            "X-Trace": "trace-id",
        },
        params={"project": "123"},
        json={"enabled": True},
    )

    message = logger.info.call_args.args
    assert "HTTP request method=GET" in message[0]
    for secret in (
        "secret-token",
        "stale-token",
        "session=secret",
        "proxy-secret",
        "cookie-secret",
        "api-secret",
    ):
        assert secret not in str(message)
    assert "trace-id" in str(message)
    assert "project" in str(message)
    assert "enabled" in str(message)
    get.assert_called_once_with(
        "https://example.com/resource",
        headers={
            "authorization": "Bearer secret-token",
            "Cookie": "session=secret",
            "Proxy-Authorization": "proxy-secret",
            "Set-Cookie": "cookie-secret",
            "X-API-Key": "api-secret",
            "X-Trace": "trace-id",
        },
        timeout=30,
        params={"project": "123"},
        json={"enabled": True},
    )
