import socket

from starlette.testclient import TestClient

import server


def _dns_result(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_validate_accepts_public_https_domain(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("142.250.184.14"))
    url = "https://www.youtube.com/watch?v=abc"
    assert server._validate_url(url) == url


def test_validate_rejects_http():
    try:
        server._validate_url("http://example.com/video")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("HTTP URL should be rejected")


def test_validate_rejects_embedded_credentials():
    try:
        server._validate_url("https://user:password@example.com/video")
    except ValueError as exc:
        assert "credenciales" in str(exc)
    else:
        raise AssertionError("URLs with embedded credentials should be rejected")


def test_validate_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("127.0.0.1"))
    try:
        server._validate_url("https://example.com/video")
    except ValueError as exc:
        assert "no pública" in str(exc)
    else:
        raise AssertionError("Private DNS result should be rejected")


def test_validate_rejects_nonstandard_port():
    try:
        server._validate_url("https://example.com:8443/video")
    except ValueError as exc:
        assert "443" in str(exc)
    else:
        raise AssertionError("Non-standard HTTPS port should be rejected")


def test_health_route_is_available():
    with TestClient(server.app, base_url="http://localhost") as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mcp_endpoint_requires_bearer_token():
    with TestClient(server.app, base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_mcp_endpoint_rejects_wrong_bearer_token():
    with TestClient(server.app, base_url="http://localhost") as client:
        response = client.post(
            "/mcp",
            headers={"Authorization": "Bearer definitely-not-the-token"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
    assert response.status_code == 401
