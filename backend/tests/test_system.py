from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "reportmind-backend"}


def test_system_status_database_failure():
    with patch("app.api.v1.system.engine.connect", side_effect=OperationalError("SELECT 1", {}, Exception("offline"))):
        response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
