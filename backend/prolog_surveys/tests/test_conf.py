import warnings

import pytest
from django.core.exceptions import ImproperlyConfigured

from prolog_surveys import conf
from prolog_surveys.identity import IdentityRequest, IdentityResult, get_identity_service


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
    del settings.PROLOG_ABANDONED_RESPONSE_DAYS
    assert conf.get("PROLOG_ABANDONED_RESPONSE_DAYS") == 90
    with pytest.raises(KeyError):
        conf.get("PROLOG_NUM_PROXIES")  # a settings.py concern, not one the app reads


# --- client key salt -----------------------------------------------------------


def test_client_key_salt_falls_back_to_secret_key(settings):
    del settings.PROLOG_CLIENT_KEY_SALT
    assert conf.get("PROLOG_CLIENT_KEY_SALT") is None
    assert conf.client_key_salt() == settings.SECRET_KEY
    under_secret_key = conf.salted_hash("203.0.113.9")
    settings.PROLOG_CLIENT_KEY_SALT = ""
    assert conf.salted_hash("203.0.113.9") == under_secret_key
    settings.PROLOG_CLIENT_KEY_SALT = "another-salt"
    assert conf.salted_hash("203.0.113.9") != under_secret_key
    conf.validate()


@pytest.mark.parametrize("salt", sorted(conf.PLACEHOLDER_SALTS - {""}))
def test_placeholder_salt_is_refused(settings, salt):
    # The salt is what keeps hashed addresses from a dictionary attack.
    settings.PROLOG_CLIENT_KEY_SALT = salt
    with pytest.raises(ImproperlyConfigured, match="PROLOG_CLIENT_KEY_SALT"):
        conf.validate()


# --- identity service -----------------------------------------------------------


class _Service:
    def create_or_link(self, request: IdentityRequest) -> IdentityResult:
        return IdentityResult(participant_pk=1)


def make_service() -> _Service:
    return _Service()


PREBUILT = _Service()


@pytest.mark.parametrize("name", ["_Service", "make_service", "PREBUILT"])
def test_identity_service_may_be_class_factory_or_instance(settings, name):
    settings.PROLOG_IDENTITY_SERVICE = f"{__name__}.{name}"
    assert isinstance(get_identity_service(), _Service)


def test_integrated_resolves_identity_service_at_startup(settings):
    settings.PROLOG_PROFILE = "integrated"
    settings.PROLOG_PARTICIPANT_MODEL = "auth.User"
    for name in ("_Service", "make_service", "PREBUILT"):
        settings.PROLOG_IDENTITY_SERVICE = f"{__name__}.{name}"
        conf.validate()
    settings.PROLOG_IDENTITY_SERVICE = "prolog_surveys.conf.THROTTLE_RATES"  # no create_or_link
    with pytest.raises(ImproperlyConfigured, match="create_or_link"):
        conf.validate()
    settings.PROLOG_IDENTITY_SERVICE = "prolog_surveys.no_such_module.Service"
    with pytest.raises(ImproperlyConfigured, match="could not be resolved"):
        conf.validate()


# --- CSRF contract with the runner ---------------------------------------------


@pytest.mark.parametrize(
    "name, value",
    [
        ("CSRF_COOKIE_HTTPONLY", True),
        ("CSRF_USE_SESSIONS", True),
        ("CSRF_COOKIE_NAME", "host_csrf"),
        ("CSRF_HEADER_NAME", "HTTP_X_HOST_CSRF"),
    ],
)
def test_integrated_warns_when_csrf_settings_break_the_runner(settings, name, value):
    settings.PROLOG_PROFILE = "integrated"
    settings.PROLOG_PARTICIPANT_MODEL = "auth.User"
    setattr(settings, name, value)
    with pytest.warns(UserWarning, match=name):
        conf.validate()


def test_default_csrf_settings_do_not_warn(settings):
    settings.PROLOG_PROFILE = "integrated"
    settings.PROLOG_PARTICIPANT_MODEL = "auth.User"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        conf.validate()


def test_env_csv_strips_and_drops_empties(monkeypatch):
    from prolog.settings import _env_csv

    monkeypatch.setenv("X_CSV", " a.org, b.org,,")
    assert _env_csv("X_CSV", "") == ["a.org", "b.org"]
    monkeypatch.delenv("X_CSV")
    assert _env_csv("X_CSV", "localhost,127.0.0.1") == ["localhost", "127.0.0.1"]
