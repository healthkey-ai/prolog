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
