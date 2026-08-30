import warnings

import pytest

# Static root only exists after collectstatic; irrelevant for tests.
warnings.filterwarnings("ignore", message="No directory at")


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
