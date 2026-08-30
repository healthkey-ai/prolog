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
