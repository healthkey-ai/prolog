"""The numbers a survey's owner asks for on day one of fieldwork.

Three of them: how many people started, how many finished, and how long
finishing took. Every one comes from what a response already records —
``started_at``, ``submitted_at`` and the status between them — so this is a
view over the responses, not a thing collected from respondents.

Definitions, because each could mean two things:

- **Respondents** — responses started against the version, whether or not
  they were finished. A respondent who opened the survey and answered
  nothing is still one; a respondent who came back and resumed is still one.
- **Completions** — responses submitted.
- **Average response time** — the mean of ``submitted_at - started_at``
  over completions only. An unfinished response has no end to measure to,
  and counting it at "so far" would only shrink as people gave up.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q

from .models import ResponseStatus, Survey, SurveyResponse


@dataclass(frozen=True)
class BasicStats:
    label: str
    respondents: int
    completions: int
    average_response_time: timedelta | None

    @property
    def completion_rate(self) -> float | None:
        return self.completions / self.respondents if self.respondents else None


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
        BasicStats(r["survey_version__version"], **{k: r[k] for k in _AGGREGATES})
        for r in responses.values("survey_version__version", "survey_version__created_at")
        .annotate(**_AGGREGATES)
        .order_by("-survey_version__created_at")
    ]
    if len(rows) != 1:
        rows.append(BasicStats("All versions", **responses.aggregate(**_AGGREGATES)))
    return rows


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
