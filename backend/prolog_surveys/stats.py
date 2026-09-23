"""The numbers a survey's owner asks for while fieldwork is running.

Every one comes from what a response already records — ``started_at``,
``submitted_at``, ``language``, ``last_question_key`` and the status between
them — so this is a view over the responses, not a thing collected from
respondents.

Definitions, because each could mean two things:

- **Respondents** — responses started against the version, whether or not
  they were finished. A respondent who opened the survey and answered
  nothing is still one; a respondent who came back and resumed is still one.
- **Completions** — responses submitted.
- **Partials** — started and not submitted. Respondents minus completions,
  named because "how many people are part-way through" is its own question.
- **Average response time** — the mean of ``submitted_at - started_at``
  over completions only. An unfinished response has no end to measure to,
  and counting it at "so far" would only shrink as people gave up.
- **By day** — starts and completions per calendar day in the deployment's
  own time zone, not UTC: a survey that opens in the evening would otherwise
  look like two days.
- **By language** — the same two counts per language, which is also how a
  translation that is failing its readers shows up.
- **Drop-off** — for responses not submitted, the question they reached
  last. Not the last one they answered: ``last_question_key`` is where the
  runner would put them back, and where somebody stopped is the question the
  instrument has to answer for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate

from .engine.visibility import iter_questions
from .models import LifecycleStatus, ResponseStatus, Survey, SurveyResponse


@dataclass(frozen=True)
class BasicStats:
    label: str
    respondents: int
    completions: int
    average_response_time: timedelta | None
    # The version these numbers are for, or None for the whole-survey row.
    # An export is per version — answers are bound to the version they were
    # given against, and two versions need not have the same columns.
    version: str | None = None

    @property
    def partials(self) -> int:
        return self.respondents - self.completions

    @property
    def completion_rate(self) -> float | None:
        return self.completions / self.respondents if self.respondents else None


@dataclass(frozen=True)
class DayRow:
    """Starts and completions on one day, in the deployment's time zone."""

    day: str
    started: int
    completed: int


@dataclass(frozen=True)
class LanguageRow:
    language: str
    respondents: int
    completions: int

    @property
    def completion_rate(self) -> float | None:
        return self.completions / self.respondents if self.respondents else None


@dataclass(frozen=True)
class DropOffRow:
    """Where unfinished responses stopped: the question they reached last."""

    question_key: str
    label: str
    count: int


_SUBMITTED = Q(status=ResponseStatus.SUBMITTED)
_DURATION = ExpressionWrapper(F("submitted_at") - F("started_at"), output_field=DurationField())
_AGGREGATES = {
    "respondents": Count("id"),
    "completions": Count("id", filter=_SUBMITTED),
    "average_response_time": Avg(_DURATION, filter=_SUBMITTED),
}


def basic_stats(survey: Survey) -> list[BasicStats]:
    """One row per version that has responses, the most recently loaded
    version first, and — when there is more than one — a last row for the
    survey as a whole. A survey nobody has answered yet is one row of zeros."""
    responses = SurveyResponse.objects.filter(survey_version__survey=survey)
    # Ordered by when the version was loaded, not by its string: "0.10.0"
    # sorts before "0.9.0" as text, and the loader stamps created_at anyway.
    rows = [
        BasicStats(
            r["survey_version__version"],
            **{k: r[k] for k in _AGGREGATES},
            version=r["survey_version__version"],
        )
        for r in responses.values("survey_version__version", "survey_version__created_at")
        .annotate(**_AGGREGATES)
        .order_by("-survey_version__created_at")
    ]
    if len(rows) != 1:
        rows.append(BasicStats("All versions", **responses.aggregate(**_AGGREGATES)))
    return rows


def by_day(survey: Survey, *, limit: int = 60) -> list[DayRow]:
    """Starts and completions per day, most recent last, at most ``limit`` days.

    Over the whole survey, not one version: fieldwork does not restart when a
    typo is corrected, and a reader asking "how is it going" means the survey.
    """
    responses = SurveyResponse.objects.filter(survey_version__survey=survey)
    started = dict(
        responses.annotate(d=TruncDate("started_at"))
        .values_list("d")
        .annotate(n=Count("id"))
        .values_list("d", "n")
    )
    completed = dict(
        responses.filter(_SUBMITTED)
        .annotate(d=TruncDate("submitted_at"))
        .values_list("d")
        .annotate(n=Count("id"))
        .values_list("d", "n")
    )
    days = sorted(d for d in {*started, *completed} if d is not None)[-limit:]
    return [DayRow(d.isoformat(), started.get(d, 0), completed.get(d, 0)) for d in days]


def by_language(survey: Survey) -> list[LanguageRow]:
    """One row per language answered in, most respondents first."""
    rows = (
        SurveyResponse.objects.filter(survey_version__survey=survey)
        .values("language")
        .annotate(respondents=Count("id"), completions=Count("id", filter=_SUBMITTED))
        .order_by("-respondents", "language")
    )
    return [LanguageRow(r["language"] or "—", r["respondents"], r["completions"]) for r in rows]


def drop_off(survey: Survey, *, limit: int = 10) -> list[DropOffRow]:
    """Where unfinished responses stopped, most common first.

    A response with no ``last_question_key`` never reached a question — it was
    opened and abandoned on the intro — and is reported as such rather than
    dropped, because "they never started" is the most actionable answer of all.
    """
    version = (
        survey.versions.filter(status=LifecycleStatus.ACTIVE).first()
        or survey.versions.order_by("-created_at").first()
    )
    counts = (
        SurveyResponse.objects.filter(survey_version__survey=survey)
        .exclude(status=ResponseStatus.SUBMITTED)
        .values("last_question_key")
        .annotate(n=Count("id"))
        .order_by("-n")
    )
    # Labelled from the version a reader is looking at now; a question only an
    # older version had keeps its key, which is still where people stopped.
    labels = (
        {
            q["key"]: str((q.get("text") or {}).get(version.definition.get("default_language"), ""))
            or q["key"]
            for _, _, q in iter_questions(version.definition)
        }
        if version
        else {}
    )
    rows = [
        DropOffRow(
            r["last_question_key"] or "", labels.get(r["last_question_key"] or "", ""), r["n"]
        )
        for r in counts
    ]
    return rows[:limit]


def format_duration(d: timedelta | None) -> str:
    """``12 min 30 s`` — what a reader does with an average, rather than
    ``0:12:30.415920``."""
    if d is None:
        return "—"
    total = round(d.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {seconds} s"
    return f"{seconds} s"
