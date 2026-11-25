"""Loopback HTTP endpoint for receiving one SolarGraf token per session."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, Lock
from typing import cast

MAX_BODY_BYTES = 16 * 1024
MAX_TOKEN_LENGTH = 8 * 1024
REQUEST_TIMEOUT_SECONDS = 5


@dataclass
class TokenSession:
    """Thread-safe state for accepting and signaling receipt of one token."""

    token: str | None = None
    received: Event = field(default_factory=Event)
    _lock: Lock = field(default_factory=Lock)

    def accept(self, token: str) -> bool:
        """Store the first token and signal waiters; reject later tokens."""
        with self._lock:
            if self.token is not None:
                return False
            self.token = token
            self.received.set()
            return True


class TokenReceiver(BaseHTTPRequestHandler):
    """Validate bounded JSON token submissions and answer with JSON status."""

    protocol_version = "HTTP/1.1"

    @property
    def session(self) -> TokenSession:
        """Return the token session associated with this server."""
        return cast(TokenHTTPServer, self.server).session

    def setup(self) -> None:
        """Initialize the request handler with a bounded socket timeout."""
        super().setup()
        self.connection.settimeout(REQUEST_TIMEOUT_SECONDS)

    def do_POST(self) -> None:
        """Accept a valid token POST at /token and reject malformed requests."""
        if self.path != "/token":
            self._send_json(404, {"error": "not_found"})
            return

        server = cast(TokenHTTPServer, self.server)
        expected_host = f"127.0.0.1:{server.server_port}"
        if self.headers.get("Host", "").lower() != expected_host:
            self._send_json(400, {"error": "invalid_host"})
            return

        content_type = self.headers.get("Content-Type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            self._send_json(415, {"error": "content_type_must_be_json"})
            return

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            self._send_json(411, {"error": "content_length_required"})
            return
        if not raw_length.isascii() or not raw_length.isdigit():
            self._send_json(400, {"error": "invalid_content_length"})
            return

        try:
            content_length = int(raw_length)
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return
        if content_length <= 0:
            self._send_json(400, {"error": "empty_body"})
            return
        if content_length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "request_body_too_large"})
            return

        try:
            body = self.rfile.read(content_length)
        except TimeoutError:
            self._send_json(408, {"error": "request_timeout"})
            return
        except OSError:
            self.close_connection = True
            return
        if len(body) != content_length:
            self._send_json(400, {"error": "incomplete_body"})
            return

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            self._send_json(400, {"error": "invalid_json"})
            return

        if not isinstance(payload, dict) or set(payload) != {"token"}:
            self._send_json(400, {"error": "invalid_request_shape"})
            return

        token = payload["token"]
        if (
            not isinstance(token, str)
            or not token.strip()
            or len(token) > MAX_TOKEN_LENGTH
            or any(
                ord(character) < 32
                or 127 <= ord(character) <= 159
                or 0xD800 <= ord(character) <= 0xDFFF
                for character in token
            )
        ):
            self._send_json(400, {"error": "invalid_token"})
            return

        if not self.session.accept(token):
            self._send_json(409, {"error": "token_already_received"})
            return

        self._send_json(200, {"status": "accepted"})

    def _send_json(self, status: int, payload: dict[str, str]) -> None:
        """Write a JSON response with explicit length and no-store headers."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        """Suppress the base handler's default request logging."""
        _ = format, args


class TokenHTTPServer(HTTPServer):
    """HTTP server that owns a single token-receiving session."""

    def __init__(self, server_address: tuple[str, int]) -> None:
        """Create the token session and bind the receiver request handler."""
        self.session = TokenSession()
        super().__init__(server_address, TokenReceiver)
