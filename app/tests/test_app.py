import os
import sys
import pytest

CURRENT_DIR = os.path.dirname(__file__)
PARENT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, os.pardir))
sys.path.insert(0, PARENT_DIR)

from main import app


@pytest.fixture
def client():
    app.testing = True
    with app.test_client() as client:
        yield client


def test_healthz_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"


def test_orders_ok(client):
    resp = client.get("/orders")
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "http_requests_total" in body
    assert "http_request_duration_seconds" in body