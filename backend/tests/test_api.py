from fastapi.testclient import TestClient

from app.main import app
from app.main import settings


def test_dashboard_endpoints_are_available_in_labeled_demo_mode():
    with TestClient(app) as client:
        overview = client.get("/api/market/overview")
        active = client.get("/api/stocks/most-active")
        premarket = client.get("/api/stocks/premarket")

    assert overview.status_code == 200
    assert overview.json()["mode"] == "demo"
    assert overview.json()["simulated"] is True
    assert active.status_code == 200
    assert active.json()["items"]
    assert premarket.status_code == 200
    assert premarket.json()["status"] == "unavailable"
    assert premarket.json()["items"] == []


def test_invalid_scanner_filters_are_rejected():
    with TestClient(app) as client:
        response = client.get("/api/stocks/most-active?sort_by=bogus")
    assert response.status_code == 422


def test_demo_stock_history_is_explicitly_simulated_and_news_is_unavailable():
    with TestClient(app) as client:
        history = client.get("/api/stocks/NVDA/history")
        news = client.get("/api/news")

    assert history.status_code == 200
    assert history.json()["simulated"] is True
    assert all(bar["simulated"] for bar in history.json()["items"])
    assert news.json()["status"] == "unavailable"


def test_private_endpoints_require_configured_admin_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "test-secret")
    with TestClient(app) as client:
        denied = client.get("/api/watchlists")
        allowed = client.get("/api/watchlists", headers={"X-Admin-Key": "test-secret"})
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert denied.status_code == 401
    assert allowed.status_code == 200