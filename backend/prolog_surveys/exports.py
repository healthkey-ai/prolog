"""Tabular export of responses and contacts (NFR-5).

One row per response, one column per question; multi-selects are exploded to
one column per option, matrices to one column per row, rankings to one
position column per item. Contacts are exported separately and are never
joined to responses.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from typing import IO, Any

from .engine.visibility import iter_questions
from .models import SurveyContact, SurveyResponse, SurveyVersion

SKIPPED = "SKIPPED"
HIDDEN = ""


def _columns(definition: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """(header, question_key, sub_key) triples in presentation order."""
    cols: list[tuple[str, str, str | None]] = []
    for _, _, q in iter_questions(definition):
        k, t, cfg = q["key"], q["type"], q.get("config", {})
        if t == "info":
            continue
        if t == "multi":
            for o in q.get("options", []):
                cols.append((f"{k}.{o['key']}", k, o["key"]))
            if any(o.get("free_text") for o in q.get("options", [])):
                cols.append((f"{k}.other_text", k, "other_text"))
        elif t == "ranking":
            for o in q.get("options", []):
                cols.append((f"{k}.{o['key']}", k, o["key"]))
            if any(o.get("free_text") for o in q.get("options", [])):
                cols.append((f"{k}.other_text", k, "other_text"))
        elif t == "matrix":
            rows = [r["key"] for r in cfg.get("rows", [])]
            if cfg.get("rows_from"):
                source = next(
                    q2 for _, _, q2 in iter_questions(definition) if q2["key"] == cfg["rows_from"]
                )
                rows = [o["key"] for o in source.get("options", [])]
            for r in rows:
                cols.append((f"{k}.{r}", k, r))
        elif t in ("single", "dropdown"):
            cols.append((k, k, None))
            if any(o.get("free_text") for o in q.get("options", [])):
                cols.append((f"{k}.other_text", k, "other_text"))
        else:
            cols.append((k, k, None))
    return cols


def _cell(value: dict[str, Any] | None, sub: str | None) -> str:
    if value is None:
        return HIDDEN
    if value.get("skipped"):
        return SKIPPED
    if sub == "other_text":
        return value.get("other_text", "")
    if "options" in value:
        return "1" if sub in value["options"] else "0"
    if "order" in value:
        return str(value["order"].index(sub) + 1) if sub in value["order"] else ""
    if "ratings" in value:
        return str(value["ratings"].get(sub, ""))
    for key in ("option", "value", "text", "number", "date"):
        if key in value:
            return str(value[key])
    if "provided" in value:
        return "1" if value["provided"] else "0"
    return ""


def response_rows(
    version: SurveyVersion, responses: Iterable[SurveyResponse]
) -> tuple[list[str], list[list[str]]]:
    cols = _columns(version.definition)
    header = [
        "response_id",
        "survey",
        "version",
        "language",
        "status",
        "started_at",
        "submitted_at",
    ] + [c[0] for c in cols]
    rows = []
    for r in responses:
        answers = r.answer_map()
        rows.append(
            [
                str(r.id),
                version.survey.slug,
                version.version,
                r.language,
                r.status,
                r.started_at.isoformat(),
                r.submitted_at.isoformat() if r.submitted_at else "",
            ]
            + [_cell(answers.get(qk), sub) for _, qk, sub in cols]
        )
    return header, rows


def write_responses(version: SurveyVersion, out: IO[str], *, submitted_only: bool = True) -> int:
    qs = version.responses.prefetch_related("answers").order_by("started_at")
    if submitted_only:
        qs = qs.filter(status="submitted")
    header, rows = response_rows(version, qs)
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return len(rows)


def write_contacts(version: SurveyVersion, out: IO[str]) -> int:
    writer = csv.writer(out)
    writer.writerow(["survey", "version", "email", "language", "created_at"])
    n = 0
    for c in SurveyContact.objects.filter(survey_version=version).order_by("created_at"):
        writer.writerow(
            [version.survey.slug, version.version, c.email, c.language, c.created_at.isoformat()]
        )
        n += 1
    return n
