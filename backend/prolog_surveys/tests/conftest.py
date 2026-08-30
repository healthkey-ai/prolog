import warnings

import pytest

# Static root only exists after collectstatic; irrelevant for tests.
warnings.filterwarnings("ignore", message="No directory at")


@pytest.fixture
def api_client():
    from rest_framework.test import APIClient

    return APIClient()
