import socket
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server


@pytest.fixture(scope="module")
def client():
    # Reuse one lifespan-managed MCP session manager for the whole test module.
    with TestClient(server.app, base_url="http://localhost") as test_client:
        yield test_client


def _dns_result(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_validate_accepts_public_https_domain(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("142.250.184.14"))
    url = "https://www.youtube.com/watch?v=abc"
    assert server._validate_url(url) == url


def test_validate_rejects_http():
    with pytest.raises(ValueError, match="HTTPS"):
        server._validate_url("http://example.com/video")


def test_validate_rejects_embedded_credentials():
    with pytest.raises(ValueError, match="credenciales"):
        server._validate_url("https://user:password@example.com/video")


def test_validate_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: _dns_result("127.0.0.1"))
    with pytest.raises(ValueError, match="no pública"):
        server._validate_url("https://example.com/video")


def test_validate_rejects_nonstandard_port():
    with pytest.raises(ValueError, match="443"):
        server._validate_url("https://example.com:8443/video")


def test_health_route_is_available(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mcp_endpoint_requires_bearer_token(client):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_mcp_endpoint_rejects_wrong_bearer_token(client):
    response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer definitely-not-the-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert response.status_code == 401
