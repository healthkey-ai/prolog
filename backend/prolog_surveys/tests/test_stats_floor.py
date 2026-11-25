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
    # 1.1's completions go with them; its 10 partials may show, as neither other count of its row does.
    assert v11["completions"] is None
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


def test_days_cannot_give_hidden_partials_away(settings, example):
    """Review of #99: completed per day added up to the hidden completions."""
    from datetime import timedelta

    from django.utils import timezone

    from prolog_surveys.models import SurveyResponse

    settings.PROLOG_STATS_MIN_COUNT = 5
    version = loader.load_definition(example).version
    responses(version, 30, submitted=27)
    now = timezone.now()
    submitted = list(
        SurveyResponse.objects.filter(status=ResponseStatus.SUBMITTED)
        .order_by("id")
        .values_list("id", flat=True)
    )
    SurveyResponse.objects.filter(id__in=submitted).update(started_at=now, submitted_at=now)
    yesterday = now - timedelta(days=1)
    SurveyResponse.objects.filter(id__in=submitted[:15]).update(
        started_at=yesterday, submitted_at=yesterday
    )

    numbers = report(version.survey)
    [row] = numbers["versions"]
    completed = [d["completed"] for d in numbers["by_day"]]

    assert (row["completions"], row["partials"]) == (None, None)
    assert None in completed  # otherwise 15 + 12 = 27 completions, and partials = 3


def test_drop_off_cannot_give_hidden_completions_away(settings, example):
    from prolog_surveys.models import SurveyResponse

    settings.PROLOG_STATS_MIN_COUNT = 5
    version = loader.load_definition(example).version
    responses(version, 30, submitted=3)
    ids = list(
        SurveyResponse.objects.exclude(status=ResponseStatus.SUBMITTED).values_list("id", flat=True)
    )
    SurveyResponse.objects.filter(id__in=ids[:15]).update(last_question_key="q1")
    SurveyResponse.objects.filter(id__in=ids[15:]).update(last_question_key="q2")

    numbers = report(version.survey)
    [row] = numbers["versions"]

    assert row["completions"] is None and row["partials"] is None
    assert None in [r["count"] for r in numbers["drop_off"]]  # otherwise 15 + 12 = 27 partials


def assert_no_lone_hidden(versions):
    """No row (completions, partials, respondents) and no column with the total
    has exactly one hidden count: it would be a subtraction away."""
    for row in versions:
        assert sum(row[k] is None for k in ("completions", "partials", "respondents")) != 1, row
    if len(versions) > 1:
        for col in ("respondents", "completions", "partials"):
            assert sum(row[col] is None for row in versions) != 1, (col, versions)


def test_a_version_cannot_be_worked_out_from_its_own_row_and_the_total(settings, two_versions):
    """Review of #99: 1.1's completions and zero partials gave its respondents, and the total gave 1.0's."""
    settings.PROLOG_STATS_MIN_COUNT = 5
    first, second = two_versions
    responses(first, 1)
    responses(second, 5, submitted=5)

    versions = report(first.survey)["versions"]

    assert versions[1]["respondents"] is None  # 1.0's one respondent
    assert_no_lone_hidden(versions)


def test_the_survey_list_hides_submitted_of_total_when_the_unfinished_are_few():
    from django.test import override_settings

    from prolog_surveys.stats import shown_submitted_of

    with override_settings(PROLOG_STATS_MIN_COUNT=5):
        assert shown_submitted_of(27, 30) is False  # 3 unfinished
        assert shown_submitted_of(20, 30) is True
        assert shown_submitted_of(30, 30) is True  # nobody unfinished: zero is nobody
        assert shown_submitted_of(2, 30) is False


def test_the_setting_is_checked():
    from django.test import override_settings

    from prolog_surveys.checks import check_settings

    for bad in (-1, "20", 2.5, True):
        with override_settings(PROLOG_STATS_MIN_COUNT=bad):
            assert [e.id for e in check_settings(None)] == ["prolog_surveys.E003"]
    with override_settings(PROLOG_STATS_MIN_COUNT=20):
        assert check_settings(None) == []
