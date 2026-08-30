import pytest


@pytest.mark.django_db
def test_health(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    body = response.json()
    assert (
        body["service"] == "PROlog" and body["status"] == "ok" and body["profile"] == "standalone"
    )
