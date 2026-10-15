from __future__ import annotations

import logging
from typing import Any

import requests


logger = logging.getLogger("mss_proposal_automation.http")
_SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


class AuthenticatedHttpClient:
    def __init__(self, timeout: float = 30) -> None:
        self.timeout = timeout
        self.session = requests.Session()

    def get(self, url: str, auth_key: str = "", **kwargs: Any):
        headers = dict(kwargs.pop("headers", {}) or {})
        if auth_key:
            headers = {
                name: value
                for name, value in headers.items()
                if name.lower() != "authorization"
            }
            headers["authorization"] = self._authorization_value(auth_key)
        timeout = kwargs.pop("timeout", self.timeout)
        logger.info(
            "HTTP request method=GET url=%s headers=%s timeout=%s params=%r "
            "data=%r json=%r",
            url,
            self._redact_headers(headers),
            timeout,
            kwargs.get("params"),
            kwargs.get("data"),
            kwargs.get("json"),
        )
        return self.session.get(url, headers=headers, timeout=timeout, **kwargs)

    @staticmethod
    def _redact_headers(headers: dict[str, Any]) -> dict[str, Any]:
        return {
            name: "<redacted>" if name.lower() in _SENSITIVE_HEADERS else value
            for name, value in headers.items()
        }

    @staticmethod
    def _authorization_value(auth_key: str) -> str:
        value = auth_key.strip()
        if value.lower().startswith("bearer "):
            return value
        return "Bearer " + value
