"""Small numbers in the report and the admin (RUN-24)."""

from __future__ import annotations

import copy

import pytest

from prolog_surveys.definitions import loader
from prolog_surveys.models import ResponseStatus
from prolog_surveys.stats import hide_small, report
from prolog_surveys.tests.conftest import make_response

pytestmark = pytest.mark.django_db


def responses(version, n, *, submitted=0, language="en"):
    for i in range(n):
        make_response(
            version,
            language=language,
            **({"status": ResponseStatus.SUBMITTED} if i < submitted else {}),
        )


@pytest.fixture
def two_versions(example):
    first = loader.load_definition(example).version
    bumped = copy.deepcopy(example)
    bumped["version"] = "1.1"
    second = loader.load_definition(bumped).version
    return first, second


def test_hide_small_hides_under_the_floor_and_never_one_alone_in_a_group():
    cells = {"a": 30, "b": 3, "c": 25, "d": 0}
    # b is under 5; alone in a group whose sum is shown, so the next smallest (c) goes too. Zero is nobody.
    assert hide_small(cells, [["a", "b", "c", "d"]], 5) == {"b", "c"}
    assert hide_small(cells, [["a", "b", "c", "d"]], 0) == set()
    assert hide_small({"a": 30, "b": 3, "c": 2}, [["a", "b", "c"]], 5) == {"b", "c"}


def test_without_a_floor_every_count_is_shown(two_versions):
    first, second = two_versions
    responses(first, 2, submitted=1)

    numbers = report(first.survey)

    # One row: a version nobody answered has none.
    assert numbers["min_count"] == 0
    assert [(v["respondents"], v["completions"], v["partials"]) for v in numbers["versions"]] == [
        (2, 1, 1)
    ]


def test_a_small_version_is_hidden_and_cannot_be_worked_out_from_the_total(settings, two_versions):
    settings.PROLOG_STATS_MIN_COUNT = 5
    first, second = two_versions
    responses(first, 3, submitted=3)
    responses(second, 30, submitted=20)

    v11, v10, total = report(first.survey)["versions"]

    assert (v10["respondents"], v10["completions"], v10["completion_rate"]) == (None, None, None)
    assert v10["average_response_time"] == "—"
    # 33 respondents in all, so 1.1's count would give 1.0's away: it is hidden too, and with its
    # completions hidden, its partials (respondents less completions) go with them.
    assert (total["respondents"], v11["respondents"]) == (33, None)
    assert (v11["completions"], v11["partials"]) == (None, None)
    assert (total["completions"], total["partials"]) == (23, 10)


def test_completions_and_partials_hide_together(settings, example):
    settings.PROLOG_STATS_MIN_COUNT = 5
    version = loader.load_definition(example).version
    responses(version, 30, submitted=27)  # 3 partials

    [row] = report(version.survey)["versions"]

    # 30 respondents are shown; 3 partials would give 27 completions away, so both go.
    assert (row["respondents"], row["completions"], row["partials"], row["completion_rate"]) == (
        30,
        None,
        None,
        None,
    )


def test_languages_days_and_drop_off_follow_the_floor(settings, example):
    settings.PROLOG_STATS_MIN_COUNT = 5
    version = loader.load_definition(example).version
    responses(version, 20, submitted=20, language="en")
    responses(version, 2, submitted=2, language="es")

    numbers = report(version.survey)
    languages = {r["language"]: r for r in numbers["by_language"]}

    assert languages["es"]["respondents"] is None and languages["en"]["respondents"] is None
    assert all(d["started"] is None or d["started"] >= 5 for d in numbers["by_day"])


def test_the_report_page_carries_the_floor(api_client, settings, example):
    from prolog_surveys.definitions.loader import publish_version

    settings.PROLOG_STATS_MIN_COUNT = 20
    settings.PROLOG_RESULTS_AUTH = f"{__name__}._viewer"
    version = loader.load_definition(example, activate=True).version
    publish_version(version)
    responses(version, 3, submitted=1)

    api_client.post(
        f"/api/run/report/{version.survey.slug}/login/",
        {"email": "r@example.org", "password": "right"},
        format="json",
    )
    stats = api_client.get(f"/api/run/report/{version.survey.slug}/").json()["stats"]

    assert stats["min_count"] == 20
    assert stats["versions"][0]["respondents"] is None


def _viewer(email, password):
    from prolog_surveys.results import ResultsViewer

    return ResultsViewer(label=email) if password == "right" else None
