"""Tabular export of responses and contacts (NFR-5).

One row per response, one column per question; multi-selects are exploded to
one column per option, matrices to one column per row, rankings to one
position column per item. Contacts are exported separately and are never
joined to responses.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from typing import IO, Any

from .engine.visibility import iter_questions, question_by_key, visible_keys
from .models import SurveyContact, SurveyResponse, SurveyVersion

SKIPPED = "SKIPPED"
HIDDEN = ""


def _columns(definition: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    """(header, question_key, sub_key) triples in presentation order."""
    cols: list[tuple[str, str, str | None]] = []
    by_key = question_by_key(definition)
    for _, _, q in iter_questions(definition):
        k, t, cfg = q["key"], q["type"], q.get("config", {})
        if t == "info":
            continue
        if t in ("multi", "ranking"):
            for o in q.get("options", []):
                cols.append((f"{k}.{o['key']}", k, o["key"]))
            if any(o.get("free_text") for o in q.get("options", [])):
                cols.append((f"{k}.other_text", k, "other_text"))
        elif t == "matrix":
            rows = [r["key"] for r in cfg.get("rows", [])]
            if cfg.get("rows_from"):
                rows = [o["key"] for o in by_key[cfg["rows_from"]].get("options", [])]
            for r in rows:
                cols.append((f"{k}.{r}", k, r))
        elif t in ("single", "dropdown"):
            cols.append((k, k, None))
            if any(o.get("free_text") for o in q.get("options", [])):
                cols.append((f"{k}.other_text", k, "other_text"))
        else:
            cols.append((k, k, None))
    return cols


def safe_cell(text: str) -> str:
    """Neutralise spreadsheet formula injection: a leading = + - @ or control
    character would be evaluated by Excel/LibreOffice/Sheets when the CSV is
    opened, so free text is prefixed with an apostrophe."""
    if text and text[0] in "=+-@\t\r":
        return "'" + text
    return text


def _cell(value: dict[str, Any] | None, sub: str | None) -> str:
    if value is None:
        return HIDDEN
    if value.get("skipped"):
        return SKIPPED
    if sub == "other_text":
        return safe_cell(value.get("other_text", ""))
    if "options" in value:
        return "1" if sub in value["options"] else "0"
    if "order" in value:
        return str(value["order"].index(sub) + 1) if sub in value["order"] else ""
    if "ratings" in value:
        return str(value["ratings"].get(sub, ""))
    if "text" in value:
        return safe_cell(str(value["text"]))
    for key in ("option", "value", "number", "date"):
        if key in value:
            return str(value[key])
    if "provided" in value:
        return "1" if value["provided"] else "0"
    return ""


def response_header(version: SurveyVersion) -> list[str]:
    return [
        "response_id",
        "survey",
        "version",
        "language",
        "status",
        "started_at",
        "submitted_at",
    ] + [c[0] for c in _columns(version.definition)]


def response_rows(
    version: SurveyVersion, responses: Iterable[SurveyResponse]
) -> Iterator[list[str]]:
    """One row per response, streamed so an export never holds every row."""
    definition = version.definition
    cols = _columns(definition)
    for r in responses:
        answers = r.answer_map()
        # A row may survive for a question the answers later hid (a contact
        # capture marker is kept so the address is never captured twice);
        # the export reports the participant's visible path only.
        visible = set(visible_keys(definition, answers))
        yield [
            str(r.id),
            version.survey.slug,
            version.version,
            r.language,
            r.status,
            r.started_at.isoformat(),
            r.submitted_at.isoformat() if r.submitted_at else "",
        ] + [_cell(answers.get(qk) if qk in visible else None, sub) for _, qk, sub in cols]


def write_responses(version: SurveyVersion, out: IO[str], *, submitted_only: bool = True) -> int:
    qs = version.responses.prefetch_related("answers").order_by("started_at")
    if submitted_only:
        qs = qs.filter(status="submitted")
    writer = csv.writer(out)
    writer.writerow(response_header(version))
    n = 0
    for row in response_rows(version, qs.iterator(chunk_size=500)):
        writer.writerow(row)
        n += 1
    return n


def write_contacts(version: SurveyVersion, out: IO[str]) -> int:
    writer = csv.writer(out)
    writer.writerow(["survey", "version", "email", "language", "captured_on"])
    n = 0
    for c in SurveyContact.objects.filter(survey_version=version).order_by("captured_on", "email"):
        writer.writerow(
            [
                version.survey.slug,
                version.version,
                safe_cell(c.email),
                c.language,
                c.captured_on.isoformat(),
            ]
        )
        n += 1
    return n
