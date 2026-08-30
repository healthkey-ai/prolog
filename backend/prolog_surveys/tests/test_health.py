import pytest

from prolog_surveys import conf


@pytest.mark.django_db
def test_health(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "PROlog"
    assert body["status"] == "ok"
    assert body["profile"] == conf.profile()
