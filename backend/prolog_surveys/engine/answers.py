"""Per-type answer validation producing canonical value shapes (RUN-15, Q-1…Q-12).

Every rejection carries a stable ``code`` plus ``params`` so the runner can show
it in the participant's language; the English ``message`` is for logs, tests
and tooling. ``frontend/src/survey/answers.ts`` mirrors the codes.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .visibility import Answers, matrix_rows

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_OTHER_TEXT = 500
# Absolute cap on a text answer (code points), whatever the definition says:
# the answer endpoint is unauthenticated, so without it one client could
# store request-sized bodies per PUT (sec.dos-unbounded). Mirrored in
# frontend/src/survey/answers.ts.
MAX_TEXT_LENGTH = 10_000

MESSAGES: dict[str, str] = {
    "info_no_answer": "info questions take no answer",
    "value_not_object": "value must be an object",
    "skip_shape": 'a skip is exactly {{"skipped": true}}',
    "skip_not_allowed": "this question cannot be skipped",
    "not_visible": "this question is not currently shown",
    "other_text_not_string": "other_text must be a string",
    "other_text_without_free_option": "other_text requires a free-text option to be selected",
    "other_text_too_long": "other_text exceeds {max} characters",
    "option_required": "option is required",
    "option_unknown": "unknown option '{option}'",
    "options_not_list": "options must be a list of option keys",
    "options_duplicate": "duplicate options",
    "options_unknown": "unknown options {options}",
    "min_selections": "select at least {min}",
    "max_selections": "select at most {max}",
    "exclusive_combined": "an exclusive option cannot be combined with others",
    "value_not_integer": "value must be an integer",
    "value_out_of_range": "value must be between {min} and {max}",
    "order_not_list": "order must be a list of option keys",
    "order_duplicate": "duplicate items in order",
    "order_unknown": "unknown items {items}",
    "order_incomplete": "every item must be ranked; missing {missing}",
    "ratings_not_object": "ratings must be an object of row -> value",
    "matrix_no_rows": "this matrix currently has no rows",
    "rows_unknown": "unknown rows {rows}",
    "rows_incomplete": "every row must be rated; missing {missing}",
    "rating_not_integer": "rating for '{row}' must be an integer",
    "rating_out_of_range": "rating for '{row}' must be between {min} and {max}",
    "text_required": "text is required",
    "text_too_long": "text exceeds {max} characters",
    "number_required": "number is required",
    "number_not_finite": "number must be finite",
    "number_not_integer": "a whole number is required",
    "number_too_small": "number must be at least {min}",
    "number_too_large": "number must be at most {max}",
    "date_format": "date must be YYYY-MM-DD",
    "date_invalid": "invalid date",
    "date_too_early": "date must be on or after {min}",
    "date_too_late": "date must be on or before {max}",
    "email_via_endpoint": "email addresses are submitted through the contact or identity endpoint",
    "unsupported_type": "unsupported question type '{type}'",
}


@dataclass(frozen=True)
class AnswerIssue:
    """One rejection: a stable code, its parameters, and an English message."""

    code: str
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def message(self) -> str:
        return MESSAGES[self.code].format(**self.params)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "params": self.params, "message": self.message}


class AnswerError(Exception):
    def __init__(self, issues: list[AnswerIssue]):
        self.issues = issues
        super().__init__("; ".join(i.message for i in issues))

    @property
    def errors(self) -> list[str]:
        return [i.message for i in self.issues]

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self.issues]

    def as_list(self) -> list[dict[str, Any]]:
        return [i.as_dict() for i in self.issues]


def issue(code: str, **params: Any) -> AnswerIssue:
    if code not in MESSAGES:
        raise KeyError(f"unknown answer issue code {code}")
    return AnswerIssue(code, params)


def _fail(code: str, **params: Any):
    raise AnswerError([issue(code, **params)])


def _option_keys(question: dict[str, Any]) -> list[str]:
    return [o["key"] for o in question.get("options", [])]


def _free_text_keys(question: dict[str, Any]) -> set[str]:
    return {o["key"] for o in question.get("options", []) if o.get("free_text")}


def _other_text(
    raw: dict[str, Any], question: dict[str, Any], selected: list[str]
) -> dict[str, Any]:
    text = raw.get("other_text")
    if text is None:
        return {}
    if not isinstance(text, str):
        _fail("other_text_not_string")
    text = text.strip()
    if not text:
        return {}
    if not (set(selected) & _free_text_keys(question)):
        _fail("other_text_without_free_option")
    if len(text) > MAX_OTHER_TEXT:
        _fail("other_text_too_long", max=MAX_OTHER_TEXT)
    return {"other_text": text}


def _skip(question: dict[str, Any], presentation: dict[str, Any]) -> dict[str, Any]:
    policy = presentation.get("skip_policy", "soft")
    if question.get("required", True) and policy == "hard":
        _fail("skip_not_allowed")
    return {"skipped": True}


def validate_answer(
    question: dict[str, Any],
    raw: Any,
    answers: Answers,
    *,
    presentation: dict[str, Any] | None = None,
    source_options: set[str] | None = None,
    questions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return the canonical value for ``raw`` or raise AnswerError.

    ``answers`` are the response's other answers and ``questions`` the
    definition's questions by key (both needed for dynamic matrix rows).
    ``source_options`` are the keys of a dropdown's ``options_source`` list
    when applicable.
    """
    presentation = presentation or {}
    questions = questions or {}
    t = question["type"]
    if t == "info":
        _fail("info_no_answer")
    if not isinstance(raw, dict):
        _fail("value_not_object")
    if raw.get("skipped"):
        if len(raw) != 1 or raw["skipped"] is not True:
            _fail("skip_shape")
        return _skip(question, presentation)
    cfg = question.get("config", {})

    if t in ("single", "dropdown"):
        option = raw.get("option")
        if not isinstance(option, str) or not option:
            _fail("option_required")
        allowed = set(_option_keys(question))
        if t == "dropdown" and cfg.get("options_source"):
            allowed |= source_options or set()
        if option not in allowed:
            _fail("option_unknown", option=option)
        return {"option": option, **_other_text(raw, question, [option])}

    if t == "multi":
        options = raw.get("options")
        if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
            _fail("options_not_list")
        if len(set(options)) != len(options):
            _fail("options_duplicate")
        allowed = _option_keys(question)
        unknown = [o for o in options if o not in allowed]
        if unknown:
            _fail("options_unknown", options=unknown)
        mn, mx = cfg.get("min_selections", 1), cfg.get("max_selections")
        if len(options) < mn:
            _fail("min_selections", min=mn)
        if mx is not None and len(options) > mx:
            _fail("max_selections", max=mx)
        exclusive = {o["key"] for o in question["options"] if o.get("exclusive")}
        if len(options) > 1 and any(o in exclusive for o in options):
            _fail("exclusive_combined")
        ordered = [o for o in allowed if o in options]
        return {"options": ordered, **_other_text(raw, question, ordered)}

    if t == "scale":
        value = raw.get("value")
        scale = cfg["scale"]
        if not isinstance(value, int) or isinstance(value, bool):
            _fail("value_not_integer")
        if not scale["min"] <= value <= scale["max"]:
            _fail("value_out_of_range", min=scale["min"], max=scale["max"])
        return {"value": value}

    if t == "ranking":
        order = raw.get("order")
        if not isinstance(order, list) or not all(isinstance(o, str) for o in order):
            _fail("order_not_list")
        if len(set(order)) != len(order):
            _fail("order_duplicate")
        allowed = _option_keys(question)
        unknown = [o for o in order if o not in allowed]
        if unknown:
            _fail("order_unknown", items=unknown)
        optional = set(cfg.get("optional_items", []))
        missing = [o for o in allowed if o not in order and o not in optional]
        if missing:
            _fail("order_incomplete", missing=missing)
        return {"order": list(order), **_other_text(raw, question, list(order))}

    if t == "matrix":
        ratings = raw.get("ratings")
        if not isinstance(ratings, dict):
            _fail("ratings_not_object")
        rows = matrix_rows(question, answers, questions)
        if not rows:
            _fail("matrix_no_rows")
        unknown = [r for r in ratings if r not in rows]
        if unknown:
            _fail("rows_unknown", rows=unknown)
        missing = [r for r in rows if r not in ratings]
        if missing:
            _fail("rows_incomplete", missing=missing)
        scale = cfg["scale"]
        for row, value in ratings.items():
            if not isinstance(value, int) or isinstance(value, bool):
                _fail("rating_not_integer", row=row)
            if not scale["min"] <= value <= scale["max"]:
                _fail("rating_out_of_range", row=row, min=scale["min"], max=scale["max"])
        return {"ratings": {r: ratings[r] for r in rows}}

    if t == "text":
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            _fail("text_required")
        limit = min(cfg.get("max_length") or MAX_TEXT_LENGTH, MAX_TEXT_LENGTH)
        if len(text) > limit:
            _fail("text_too_long", max=limit)
        return {"text": text.strip()}

    if t == "number":
        number = raw.get("number")
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            _fail("number_required")
        if isinstance(number, float) and not math.isfinite(number):
            _fail("number_not_finite")
        if cfg.get("integer") and int(number) != number:
            _fail("number_not_integer")
        lo, hi = cfg.get("min_value"), cfg.get("max_value")
        if lo is not None and number < lo:
            _fail("number_too_small", min=lo)
        if hi is not None and number > hi:
            _fail("number_too_large", max=hi)
        return {"number": int(number) if cfg.get("integer") else number}

    if t == "date":
        value = raw.get("date")
        if not isinstance(value, str) or not DATE_RE.match(value):
            _fail("date_format")
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            _fail("date_invalid")
        lo, hi = cfg.get("min_date"), cfg.get("max_date")
        if lo and value < lo:
            _fail("date_too_early", min=lo)
        if hi and value > hi:
            _fail("date_too_late", max=hi)
        return {"date": value}

    if t == "email":
        # The address itself never travels through the answer endpoint (CON-3/4).
        if raw.get("provided") is False and len(raw) == 1:
            return {"provided": False}
        _fail("email_via_endpoint")

    _fail("unsupported_type", type=t)
    return {}  # pragma: no cover


def option_keys_of(value: dict[str, Any]) -> list[str]:
    """Option keys carried by a canonical value, for indexing."""
    if "option" in value:
        return [value["option"]]
    if "options" in value:
        return list(value["options"])
    if "order" in value:
        return list(value["order"])
    return []
