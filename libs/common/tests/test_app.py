from fastapi.testclient import TestClient

from farm_common.app import create_app


def test_health_reports_service_name_and_version():
    client = TestClient(create_app("demo", "1.2.3"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "demo", "version": "1.2.3"}
