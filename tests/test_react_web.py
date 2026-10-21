from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from aml_poc.web import app


def test_react_proxy_preserves_uploads_queries_and_rejections():
    async def send(client, request, **kwargs):
        assert request.url.path == "/documents/extract"
        assert request.url.params["test"] == "1"
        assert request.headers["content-type"] == "multipart/form-data; boundary=demo"
        assert request.content == b"document bytes"
        return httpx.Response(409, json={"detail": "Evidence changed"}, request=request)

    with TestClient(app) as client, patch.object(httpx.AsyncClient, "send", send):
        response = client.post(
            "/backend/documents/extract?test=1",
            content=b"document bytes",
            headers={"content-type": "multipart/form-data; boundary=demo"},
        )
        assert response.status_code == 409
        assert response.json() == {"detail": "Evidence changed"}


def test_react_kyc_proxy_uses_database_route_and_handles_outage():
    async def send(client, request, **kwargs):
        assert request.url.path == "/api/customers/C003"
        raise httpx.ConnectError("unreachable", request=request)

    with TestClient(app) as client, patch.object(httpx.AsyncClient, "send", send):
        response = client.get("/api/customers/C003")
        assert response.status_code == 503
        assert "Python API" in response.json()["detail"]


def test_react_deep_links_and_missing_build(tmp_path):
    from aml_poc import web

    with patch.object(web, "DIST", tmp_path), TestClient(app) as client:
        assert client.get("/investigations/A001").status_code == 503
        (tmp_path / "index.html").write_text("<html>React console</html>")
        response = client.get("/investigations/A001?section=Customer%20KYC")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"
        assert "React console" in response.text


def test_api_accepts_backend_prefix():
    from types import SimpleNamespace

    from aml_poc.api import create_app

    with TestClient(create_app(service=SimpleNamespace(mode="demo"))) as client:
        assert client.get("/backend/health").json() == {"status": "ok", "mode": "demo"}


def test_legacy_kyc_links_redirect_to_console(monkeypatch):
    from types import SimpleNamespace

    from aml_poc.api import create_app

    monkeypatch.setenv("AML_CONSOLE_URL", "http://localhost:8502")
    with TestClient(create_app(service=SimpleNamespace(mode="demo"))) as client:
        response = client.get("/kyc/C003?tab=transactions", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "http://localhost:8502/kyc/C003?tab=transactions"
