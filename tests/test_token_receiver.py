import json
import socket
import sys
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from token_receiver import MAX_BODY_BYTES, TokenHTTPServer


@pytest.fixture
def token_server():
    server = TokenHTTPServer(("127.0.0.1", 0))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _post(server, body, content_type="application/json"):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(
        "POST",
        "/token",
        body=body,
        headers={"Content-Type": content_type},
    )
    response = connection.getresponse()
    result = response.status, json.loads(response.read())
    connection.close()
    return result


def test_receiver_preserves_raw_token_and_accepts_only_one(token_server):
    token = "token-value-with-both-edge-characters"

    status, payload = _post(token_server, json.dumps({"token": token}).encode("utf-8"))

    assert status == 200
    assert payload == {"status": "accepted"}
    assert token_server.session.token == token
    assert token_server.session.received.is_set()

    status, payload = _post(
        token_server, json.dumps({"token": "second-token"}).encode("utf-8")
    )
    assert status == 409
    assert payload == {"error": "token_already_received"}
    assert token_server.session.token == token


@pytest.mark.parametrize(
    ("body", "content_type", "expected_status", "expected_error"),
    [
        (b"{invalid json", "application/json", 400, "invalid_json"),
        (
            json.dumps({"token": 123}).encode("utf-8"),
            "application/json",
            400,
            "invalid_token",
        ),
        (
            json.dumps({"token": "token", "extra": True}).encode("utf-8"),
            "application/json",
            400,
            "invalid_request_shape",
        ),
        (b'{"token":"token"}', "text/plain", 415, "content_type_must_be_json"),
    ],
)
def test_receiver_rejects_malformed_requests_without_setting_token(
    token_server, body, content_type, expected_status, expected_error
):
    status, payload = _post(token_server, body, content_type)

    assert status == expected_status
    assert payload == {"error": expected_error}
    assert token_server.session.token is None
    assert not token_server.session.received.is_set()


def test_receiver_rejects_oversized_body(token_server):
    status, payload = _post(
        token_server,
        b"x" * (MAX_BODY_BYTES + 1),
    )

    assert status == 413
    assert payload == {"error": "request_body_too_large"}
    assert token_server.session.token is None


@pytest.mark.parametrize(
    ("content_length", "expected_status", "expected_error"),
    [
        (None, 411, "content_length_required"),
        ("not-a-number", 400, "invalid_content_length"),
    ],
)
def test_receiver_handles_missing_or_invalid_content_length(
    token_server, content_length, expected_status, expected_error
):
    headers = [
        f"Host: 127.0.0.1:{token_server.server_port}",
        "Content-Type: application/json",
        "Connection: close",
    ]
    if content_length is not None:
        headers.append(f"Content-Length: {content_length}")
    request = ("POST /token HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n").encode(
        "ascii"
    )
    with socket.create_connection(
        ("127.0.0.1", token_server.server_port), timeout=5
    ) as connection:
        connection.sendall(request)
        chunks = []
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        response = b"".join(chunks).decode("utf-8")

    assert response.splitlines()[0].split()[1] == str(expected_status)
    assert json.loads(response.split("\r\n\r\n", 1)[1]) == {"error": expected_error}
    assert token_server.session.token is None
