import warnings

import pytest
from django.core.exceptions import ImproperlyConfigured

from prolog_surveys import conf
from prolog_surveys.identity import IdentityRequest, IdentityResult, get_identity_service


@pytest.fixture(autouse=True)
def _participant_factory(settings):
    """The integrated profile refuses to start without one (DEP-2), and several
    tests below switch profile mid-test. Harmless in standalone, which does not
    look at it."""
    settings.PROLOG_PARTICIPANT_FACTORY = f"{__name__}.resolve_nobody"


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


# --- participant resolver --------------------------------------------------------


def resolve_nobody(request):
    return None


@pytest.mark.parametrize("profile, model", [("standalone", None), ("integrated", "auth.User")])
def test_participant_resolver_is_resolved_at_startup(settings, profile, model):
    settings.PROLOG_PROFILE = profile
    settings.PROLOG_PARTICIPANT_MODEL = model
    settings.PROLOG_PARTICIPANT_RESOLVER = f"{__name__}.resolve_nobody"
    conf.validate()
    settings.PROLOG_PARTICIPANT_RESOLVER = "prolog_surveys.no_such_module.resolve"
    with pytest.raises(ImproperlyConfigured, match="PROLOG_PARTICIPANT_RESOLVER"):
        conf.validate()
    settings.PROLOG_PARTICIPANT_RESOLVER = "prolog_surveys.conf.THROTTLE_RATES"  # not callable
    with pytest.raises(ImproperlyConfigured, match="callable"):
        conf.validate()


# --- throttle rates ---------------------------------------------------------------


@pytest.mark.parametrize("rate", ["30/hour", "30/h", "1/sec", "5/minute", "100/day"])
def test_throttle_rate_accepts_what_drf_parses(rate):
    assert conf.THROTTLE_RATE_RE.match(rate)


@pytest.mark.parametrize("rate", ["30 per hour", "30/week", "thirty/hour", "30/", "30", ""])
def test_throttle_rate_is_validated_at_startup(settings, rate):
    # DRF only parses a rate in the throttle's __init__, i.e. on the first
    # request; a bad value must not get past boot and the health check.
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {**conf.THROTTLE_RATES, "run.create": rate},
    }
    with pytest.raises(ImproperlyConfigured, match="run.create"):
        conf.validate()


def test_settings_reject_bad_throttle_env(monkeypatch):
    from prolog.settings import _throttle_rates

    monkeypatch.setenv("PROLOG_THROTTLE_CREATE", "30 per hour")
    with pytest.raises(ImproperlyConfigured, match="PROLOG_THROTTLE_CREATE"):
        _throttle_rates()
    monkeypatch.setenv("PROLOG_THROTTLE_CREATE", "45/hour")
    assert _throttle_rates()["run.create"] == "45/hour"
    monkeypatch.setenv("PROLOG_THROTTLE_CREATE", "")  # unset, like the other PROLOG_* values
    assert _throttle_rates()["run.create"] == conf.THROTTLE_RATES["run.create"]


def test_integrated_profile_requires_a_participant_factory(settings):
    """Every response is bound to a participant and the column is not nullable,
    so a deployment that cannot produce one cannot serve a survey at all."""
    settings.PROLOG_PROFILE = "integrated"
    settings.PROLOG_PARTICIPANT_MODEL = "auth.User"
    settings.PROLOG_PARTICIPANT_FACTORY = None

    with pytest.raises(ImproperlyConfigured, match="PROLOG_PARTICIPANT_FACTORY"):
        conf.validate()
