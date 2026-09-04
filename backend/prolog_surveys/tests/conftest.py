import warnings
from pathlib import Path

import pytest

from prolog_surveys.definitions.schema import read_json

# Static root only exists after collectstatic; irrelevant for tests.
warnings.filterwarnings("ignore", message="No directory at")

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples"
EXAMPLE_PATH = EXAMPLES_DIR / "sample-wellbeing.json"


def example_definition() -> dict:
    """A fresh copy of the neutral sample instrument (tests mutate it freely)."""
    return read_json(EXAMPLE_PATH)


@pytest.fixture
def example() -> dict:
    return example_definition()


def make_response(version, **fields):
    """A response against ``version``, in either profile.

    The integrated profile requires a participant on every response (DEP-2,
    RUN-2), so a test that builds one directly has to mint one the way the
    runner does; standalone has no such column and mint_participant returns
    None. Tests that want a response and do not care which profile they are in
    go through here.
    """
    from prolog_surveys.identity import mint_participant
    from prolog_surveys.models import SurveyResponse

    participant = mint_participant()
    if participant is not None:
        # mint_participant returns the pk, which is what the runner stores.
        fields["participant_id"] = participant
    return SurveyResponse.objects.create(survey_version=version, **fields)


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Throttle counters live in the cache; keep tests independent."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
