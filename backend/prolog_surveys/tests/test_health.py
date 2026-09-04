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


@pytest.mark.django_db
def test_health_caches_applied_migrations(api_client, monkeypatch):
    from prolog_surveys import views

    monkeypatch.setattr(views, "_migrations_applied", False)
    assert api_client.get("/api/health/").json()["checks"]["migrations"] == "applied"
    assert views._migrations_applied is True

    def boom(*a, **k):
        raise AssertionError("migration graph rebuilt after it was known to be applied")

    monkeypatch.setattr(views, "MigrationExecutor", boom)
    assert api_client.get("/api/health/").status_code == 200
