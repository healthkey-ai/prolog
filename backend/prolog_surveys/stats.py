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

Small numbers (RUN-24): ``report`` is what a reader sees, with
``PROLOG_STATS_MIN_COUNT`` applied. A count from 1 to N-1 is hidden; where
that leaves exactly one hidden count in a group whose sum is shown (versions
against the total, completions and partials against respondents, days,
languages, questions), the next smallest is hidden too, so no hidden count is
a subtraction away. A rate or an average over a hidden count is hidden.
Zero is shown: it is nobody.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncDate

from . import conf
from .engine.visibility import iter_questions
from .exports import is_linked_capture
from .models import (
    LifecycleStatus,
    ResponseStatus,
    Survey,
    SurveyContact,
    SurveyLinkedContact,
    SurveyResponse,
)


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


def contact_counts(survey: Survey) -> dict[str, int]:
    """How many addresses each version's export will contain, by version.

    A version keeps addresses in one table or the other, and its capture mode
    says which (``is_linked_capture``). Counting both would promise rows the
    export does not produce: a version whose mode changed while it was still a
    draft can have rows in the table it no longer reads, and those are not what
    a reader is about to download.
    """
    unlinked = dict(
        SurveyContact.objects.filter(survey_version__survey=survey)
        .values_list("survey_version__version")
        .annotate(n=Count("id"))
    )
    linked = dict(
        SurveyLinkedContact.objects.filter(response__survey_version__survey=survey)
        .values_list("response__survey_version__version")
        .annotate(n=Count("id"))
    )
    counts: dict[str, int] = {}
    for version in survey.versions.all():
        source = linked if is_linked_capture(version.definition) else unlinked
        counts[version.version] = source.get(version.version, 0)
    return counts


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


def hide_small(cells: dict, groups: list[list], n: int) -> set:
    """The keys of ``cells`` (counts) not to show: every count from 1 to n-1,
    and, wherever that leaves exactly one hidden in a group whose sum is
    shown, the smallest other count in it, until no group has exactly one."""
    if n <= 1:
        return set()
    hidden = {k for k, v in cells.items() if 0 < v < n}
    changed = True
    while changed:
        changed = False
        for group in groups:
            if sum(k in hidden for k in group) != 1:
                continue
            others = [k for k in group if k not in hidden and cells[k] > 0]
            if others:
                hidden.add(min(others, key=lambda k: cells[k]))
                changed = True
    return hidden


def report(survey: Survey) -> dict:
    """The report's numbers, as a reader sees them: ``None`` for a count not
    shown, and ``min_count`` saying under what (RUN-24)."""
    n = int(conf.get("PROLOG_STATS_MIN_COUNT") or 0)
    rows = basic_stats(survey)
    contacts = contact_counts(survey)
    days = by_day(survey)
    languages = by_language(survey)
    stops = drop_off(survey)

    cells: dict = {}
    # Each group is a set of counts that add up, with the count holding their
    # sum among them: hiding exactly one count in a group would let it be
    # worked out from the others, the sum included.
    groups: list[list] = []
    for i, r in enumerate(rows):
        cells[("v", i, "respondents")] = r.respondents
        cells[("v", i, "completions")] = r.completions
        cells[("v", i, "partials")] = r.partials
        cells[("v", i, "contacts")] = contacts.get(
            r.version, sum(contacts.values()) if r.version is None else 0
        )
        groups.append([("v", i, "completions"), ("v", i, "partials"), ("v", i, "respondents")])
    versions = [i for i, r in enumerate(rows) if r.version is not None]
    total = len(rows) - 1  # the "All versions" row, or the one version's own
    if len(versions) > 1:
        for col in ("respondents", "completions", "partials", "contacts"):
            groups.append([*(("v", i, col) for i in versions), ("v", total, col)])
    for i, r in enumerate(languages):
        cells[("l", i, "respondents")] = r.respondents
        cells[("l", i, "completions")] = r.completions
        # Not shown, but respondents less completions: hidden with them.
        cells[("l", i, "partials")] = r.respondents - r.completions
        groups.append([("l", i, "completions"), ("l", i, "partials"), ("l", i, "respondents")])
    for col in ("respondents", "completions"):
        groups.append([*(("l", i, col) for i in range(len(languages))), ("v", total, col)])
    for i, d in enumerate(days):
        cells[("d", i, "started")] = d.started
        cells[("d", i, "completed")] = d.completed
    # Days and drop-off are lists cut short (60 days, 10 questions): their
    # total only adds up, and only joins the group, when nothing was cut.
    for col, against in (("started", "respondents"), ("completed", "completions")):
        group = [("d", i, col) for i in range(len(days))]
        if sum(cells[k] for k in group) == cells.get(("v", total, against), -1):
            group.append(("v", total, against))
        groups.append(group)
    for i, r in enumerate(stops):
        cells[("q", i, "count")] = r.count
    group = [("q", i, "count") for i in range(len(stops))]
    if sum(cells[k] for k in group) == cells.get(("v", total, "partials"), -1):
        group.append(("v", total, "partials"))
    groups.append(group)

    hidden = hide_small(cells, groups, n)

    def shown(*key):
        return None if key in hidden else cells[key]

    def version_row(i: int, r: BasicStats) -> dict:
        respondents, completions = shown("v", i, "respondents"), shown("v", i, "completions")
        return {
            "label": r.label,
            "version": r.version,
            "respondents": respondents,
            "completions": completions,
            "contacts": shown("v", i, "contacts"),
            "partials": shown("v", i, "partials"),
            "completion_rate": None
            if respondents is None or completions is None
            else r.completion_rate,
            "average_response_time": "—"
            if completions is None
            else format_duration(r.average_response_time),
        }

    return {
        "min_count": n,
        "versions": [version_row(i, r) for i, r in enumerate(rows)],
        "by_day": [
            {
                "day": d.day,
                "started": shown("d", i, "started"),
                "completed": shown("d", i, "completed"),
            }
            for i, d in enumerate(days)
        ],
        "by_language": [
            {
                "language": r.language,
                "respondents": shown("l", i, "respondents"),
                "completions": shown("l", i, "completions"),
            }
            for i, r in enumerate(languages)
        ],
        "drop_off": [
            {"question_key": r.question_key, "label": r.label, "count": shown("q", i, "count")}
            for i, r in enumerate(stops)
        ],
    }


def shown_submitted_of(completed: int, total: int) -> bool:
    """Whether the survey list may show "submitted/total": not when either,
    or the unfinished between them, is a small group (RUN-24)."""
    n = int(conf.get("PROLOG_STATS_MIN_COUNT") or 0)
    return not any(0 < v < n for v in (completed, total, total - completed))


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
