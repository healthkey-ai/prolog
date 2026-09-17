"""Tabular export of responses and contacts (NFR-5).

One row per response, one column per question; multi-selects are exploded to
one column per option, matrices to one column per row, rankings to one
position column per item. Contacts are exported separately and are never
joined to responses.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator, Sequence
from typing import IO, Any

from .engine.answers import NOT_APPLICABLE
from .engine.visibility import iter_questions, question_by_key, visible_keys
from .models import SurveyContact, SurveyLinkedContact, SurveyResponse, SurveyVersion

SKIPPED = "SKIPPED"
# A consent given and later withdrawn (withdraw_consent): distinct from never given.
WITHDRAWN = "WITHDRAWN"
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
        elif t == "email":
            cols.append((k, k, None))
            # One column per consent offered: what was ticked with the address
            # is the record a controller acts on, so it travels with the answers.
            for c in cfg.get("consents", []):
                cols.append((f"{k}.consent.{c['key']}", k, f"consent:{c['key']}"))
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


def _cell(
    value: dict[str, Any] | None, sub: str | None, withdrawn: frozenset[str] = frozenset()
) -> str:
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
        rating = value["ratings"].get(sub, "")
        # A row that does not apply is a recorded answer, distinct from a
        # skipped question (SKIPPED) and a row never reached (blank), and it
        # must never sit in a numeric column as a number.
        return "NA" if rating == NOT_APPLICABLE else str(rating)
    if "text" in value:
        return safe_cell(str(value["text"]))
    for key in ("option", "value", "number", "date"):
        if key in value:
            return str(value[key])
    if "provided" in value:
        if sub and sub.startswith("consent:"):
            key = sub[len("consent:") :]
            # Given, given then withdrawn, or never given: a controller needs
            # all three, so a withdrawal is not exported as a plain 0.
            if key in withdrawn:
                return WITHDRAWN
            return "1" if key in value.get("consents", []) else "0"
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
        # Identity capture keeps each consent as a row; a withdrawn one shows as such.
        withdrawn = frozenset(c.key for c in r.capture_consents.all() if c.withdrawn_at)
        yield [
            str(r.id),
            version.survey.slug,
            version.version,
            r.language,
            r.status,
            r.started_at.isoformat(),
            r.submitted_at.isoformat() if r.submitted_at else "",
        ] + [
            _cell(answers.get(qk) if qk in visible else None, sub, withdrawn) for _, qk, sub in cols
        ]


def write_responses(version: SurveyVersion, out: IO[str], *, submitted_only: bool = True) -> int:
    qs = version.responses.prefetch_related("answers", "capture_consents").order_by("started_at")
    if submitted_only:
        qs = qs.filter(status="submitted")
    writer = csv.writer(out)
    writer.writerow(response_header(version))
    n = 0
    for row in response_rows(version, qs.iterator(chunk_size=500)):
        writer.writerow(row)
        n += 1
    return n


def _email_config(definition: dict[str, Any]) -> dict[str, Any]:
    for _, _, q in iter_questions(definition):
        if q["type"] == "email":
            return q.get("config") or {}
    return {}


def _consent_keys(definition: dict[str, Any]) -> list[str]:
    return [c["key"] for c in _email_config(definition).get("consents", [])]


def _consent_cells(consents: list[dict[str, Any]] | None, keys: list[str]) -> list[str]:
    ticked = {c["key"]: c.get("withdrawn_on") for c in consents or []}
    return [(WITHDRAWN if ticked[k] else "1") if k in ticked else "0" for k in keys]


def write_contacts(version: SurveyVersion, out: IO[str]) -> int:
    """The addresses of a version. Unlinked contact capture: one row per
    address, nothing that reaches a response. Linked contact capture: one row
    per response that gave one, keyed by ``response_id`` — the join to the
    response export is deliberate, and the only place it exists."""
    consent_keys = _consent_keys(version.definition)
    linked = bool(_email_config(version.definition).get("link_response"))
    writer = csv.writer(out)
    writer.writerow(
        ["survey", "version"]
        + (["response_id"] if linked else [])
        + ["email", "language", "captured_at" if linked else "captured_on"]
        + [f"consent.{k}" for k in consent_keys]
    )
    n = 0
    # Streamed like the responses: a long-running instrument holds as many
    # contacts as submitted responses.
    if linked:
        rows = (
            SurveyLinkedContact.objects.filter(response__survey_version=version)
            .order_by("captured_at", "response_id")
            .values_list("response_id", "email", "language", "captured_at", "consents")
        )
        for rid, email, language, captured_at, consents in rows.iterator(chunk_size=1000):
            writer.writerow(
                [version.survey.slug, version.version, str(rid), safe_cell(email), language]
                + [captured_at.isoformat()]
                + _consent_cells(consents, consent_keys)
            )
            n += 1
        return n
    rows = (
        SurveyContact.objects.filter(survey_version=version)
        .order_by("captured_on", "email")
        .values_list("email", "language", "captured_on", "consents")
    )
    for email, language, captured_on, consents in rows.iterator(chunk_size=1000):
        writer.writerow(
            [version.survey.slug, version.version, safe_cell(email), language]
            + [captured_on.isoformat()]
            + _consent_cells(consents, consent_keys)
        )
        n += 1
    return n


# --- translations -----------------------------------------------------------

TRANSLATION_HEADER = ("path", "status", "source", "target")


def translation_rows(
    definition: dict[str, Any], language: str, *, against: str | None = None
) -> Iterator[tuple[str, str, str, str]]:
    """Every translatable string as (path, status, source text, target text).

    In presentation order, from the same inventory the validator uses — a
    second walker would drift, and the strings it missed would be exactly the
    ones nobody reviewed.

    A missing translation yields an empty target rather than no row: the gaps
    are what a reviewer most needs to see.
    """
    from .definitions.validate import walk_i18n

    source_lang = against or definition.get("default_language", "en")
    status = (definition.get("translation_status") or {}).get(language, "")
    for path, text in walk_i18n(definition):
        yield (
            path,
            status,
            safe_cell(str(text.get(source_lang, ""))),
            safe_cell(str(text.get(language, ""))),
        )


def translation_matrix(
    definition: dict[str, Any], languages: Sequence[str], *, against: str | None = None
) -> Iterator[tuple[str, ...]]:
    """Every translatable string with all of its translations on one row.

    The pair export (``translation_rows``) is for a reviewer working through
    one language. This is for seeing the instrument whole: what each string
    says in every language it is offered in, gaps included.
    """
    from .definitions.validate import walk_i18n

    source_lang = against or definition.get("default_language", "en")
    for path, text in walk_i18n(definition):
        yield (
            path,
            safe_cell(str(text.get(source_lang, ""))),
            *(safe_cell(str(text.get(lang, ""))) for lang in languages),
        )


def matrix_header(
    definition: dict[str, Any], languages: Sequence[str], *, against: str | None = None
) -> tuple[str, ...]:
    """``path``, the source language, then each language with its review state.

    The state belongs in the header because it is a property of the language,
    not of the string: repeating "machine" on all 300 rows says it 300 times
    and still leaves a reader guessing which column it applies to.
    """
    source_lang = against or definition.get("default_language", "en")
    status = definition.get("translation_status") or {}
    return (
        "path",
        source_lang,
        *(f"{lang} ({status.get(lang, 'unset')})" for lang in languages),
    )


def write_translation_matrix(
    definition: dict[str, Any],
    out: IO[str],
    *,
    languages: Sequence[str],
    against: str | None = None,
    markdown: bool = False,
) -> int:
    """Write every language side by side. Returns the number of strings."""
    header = matrix_header(definition, languages, against=against)
    rows = list(translation_matrix(definition, languages, against=against))
    _write_table(out, header, rows, markdown=markdown)
    return len(rows)


def _write_table(
    out: IO[str], header: Sequence[str], rows: Sequence[Sequence[str]], *, markdown: bool
) -> None:
    if markdown:
        out.write("| " + " | ".join(header) + " |\n")
        out.write("|" + "|".join(["---"] * len(header)) + "|\n")
        for row in rows:
            # A literal pipe would end the cell and shift every column after it.
            out.write("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |\n")
        return
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)


def write_translations(
    definition: dict[str, Any],
    out: IO[str],
    *,
    language: str,
    against: str | None = None,
    markdown: bool = False,
) -> int:
    """Write the side-by-side review sheet. Returns the number of strings."""
    source_lang = against or definition.get("default_language", "en")
    header = ("path", "status", source_lang, language)
    rows = list(translation_rows(definition, language, against=against))
    _write_table(out, header, rows, markdown=markdown)
    return len(rows)
