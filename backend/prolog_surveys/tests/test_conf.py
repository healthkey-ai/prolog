import pytest
from django.core.exceptions import ImproperlyConfigured

from prolog_surveys import conf


def test_standalone_rejects_participant_model(settings):
    settings.PROLOG_PROFILE = "standalone"
    settings.PROLOG_PARTICIPANT_MODEL = "auth.User"
    with pytest.raises(ImproperlyConfigured):
        conf.validate()


def test_integrated_requires_participant_model(settings):
    settings.PROLOG_PROFILE = "integrated"
    settings.PROLOG_PARTICIPANT_MODEL = None
    with pytest.raises(ImproperlyConfigured):
        conf.validate()


def test_defaults_apply(settings):
    del settings.PROLOG_CLIENT_KEY_SALT
    assert conf.get("PROLOG_CLIENT_KEY_SALT") == "prolog"


def test_env_csv_strips_and_drops_empties(monkeypatch):
    from prolog.settings import _env_csv

    monkeypatch.setenv("X_CSV", " a.org, b.org,,")
    assert _env_csv("X_CSV", "") == ["a.org", "b.org"]
    monkeypatch.delenv("X_CSV")
    assert _env_csv("X_CSV", "localhost,127.0.0.1") == ["localhost", "127.0.0.1"]
