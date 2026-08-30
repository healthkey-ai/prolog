"""Per-type answer validation producing canonical value shapes (RUN-15, Q-1…Q-12)."""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .visibility import Answers, matrix_rows

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_OTHER_TEXT = 500


@dataclass
class AnswerError(Exception):
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return "; ".join(self.errors)


def _fail(*errors: str):
    raise AnswerError(list(errors))


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
        _fail("other_text must be a string")
    text = text.strip()
    if not text:
        return {}
    if not (set(selected) & _free_text_keys(question)):
        _fail("other_text requires a free-text option to be selected")
    if len(text) > MAX_OTHER_TEXT:
        _fail(f"other_text exceeds {MAX_OTHER_TEXT} characters")
    return {"other_text": text}


def _skip(question: dict[str, Any], presentation: dict[str, Any]) -> dict[str, Any]:
    policy = presentation.get("skip_policy", "soft")
    if question.get("required", True) and policy == "hard":
        _fail("this question cannot be skipped")
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
        _fail("info questions take no answer")
    if not isinstance(raw, dict):
        _fail("value must be an object")
    if raw.get("skipped"):
        if len(raw) != 1 or raw["skipped"] is not True:
            _fail('a skip is exactly {"skipped": true}')
        return _skip(question, presentation)
    cfg = question.get("config", {})

    if t in ("single", "dropdown"):
        option = raw.get("option")
        if not isinstance(option, str) or not option:
            _fail("option is required")
        allowed = set(_option_keys(question))
        if t == "dropdown" and cfg.get("options_source"):
            allowed |= source_options or set()
        if option not in allowed:
            _fail(f"unknown option '{option}'")
        return {"option": option, **_other_text(raw, question, [option])}

    if t == "multi":
        options = raw.get("options")
        if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
            _fail("options must be a list of option keys")
        if len(set(options)) != len(options):
            _fail("duplicate options")
        allowed = _option_keys(question)
        unknown = [o for o in options if o not in allowed]
        if unknown:
            _fail(f"unknown options {unknown}")
        mn, mx = cfg.get("min_selections", 1), cfg.get("max_selections")
        if len(options) < mn:
            _fail(f"select at least {mn}")
        if mx is not None and len(options) > mx:
            _fail(f"select at most {mx}")
        exclusive = {o["key"] for o in question["options"] if o.get("exclusive")}
        if len(options) > 1 and any(o in exclusive for o in options):
            _fail("an exclusive option cannot be combined with others")
        ordered = [o for o in allowed if o in options]
        return {"options": ordered, **_other_text(raw, question, ordered)}

    if t == "scale":
        value = raw.get("value")
        scale = cfg["scale"]
        if not isinstance(value, int) or isinstance(value, bool):
            _fail("value must be an integer")
        if not scale["min"] <= value <= scale["max"]:
            _fail(f"value must be between {scale['min']} and {scale['max']}")
        return {"value": value}

    if t == "ranking":
        order = raw.get("order")
        if not isinstance(order, list) or not all(isinstance(o, str) for o in order):
            _fail("order must be a list of option keys")
        if len(set(order)) != len(order):
            _fail("duplicate items in order")
        allowed = _option_keys(question)
        unknown = [o for o in order if o not in allowed]
        if unknown:
            _fail(f"unknown items {unknown}")
        optional = set(cfg.get("optional_items", []))
        missing = [o for o in allowed if o not in order and o not in optional]
        if missing:
            _fail(f"every item must be ranked; missing {missing}")
        return {"order": list(order), **_other_text(raw, question, list(order))}

    if t == "matrix":
        ratings = raw.get("ratings")
        if not isinstance(ratings, dict):
            _fail("ratings must be an object of row -> value")
        rows = matrix_rows(question, answers, questions)
        if not rows:
            _fail("this matrix currently has no rows")
        unknown = [r for r in ratings if r not in rows]
        if unknown:
            _fail(f"unknown rows {unknown}")
        missing = [r for r in rows if r not in ratings]
        if missing:
            _fail(f"every row must be rated; missing {missing}")
        scale = cfg["scale"]
        for row, value in ratings.items():
            if not isinstance(value, int) or isinstance(value, bool):
                _fail(f"rating for '{row}' must be an integer")
            if not scale["min"] <= value <= scale["max"]:
                _fail(f"rating for '{row}' must be between {scale['min']} and {scale['max']}")
        return {"ratings": {r: ratings[r] for r in rows}}

    if t == "text":
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            _fail("text is required")
        limit = cfg.get("max_length")
        if limit and len(text) > limit:
            _fail(f"text exceeds {limit} characters")
        return {"text": text.strip()}

    if t == "number":
        number = raw.get("number")
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            _fail("number is required")
        if isinstance(number, float) and not math.isfinite(number):
            _fail("number must be finite")
        if cfg.get("integer") and int(number) != number:
            _fail("a whole number is required")
        lo, hi = cfg.get("min_value"), cfg.get("max_value")
        if lo is not None and number < lo:
            _fail(f"number must be at least {lo}")
        if hi is not None and number > hi:
            _fail(f"number must be at most {hi}")
        return {"number": int(number) if cfg.get("integer") else number}

    if t == "date":
        value = raw.get("date")
        if not isinstance(value, str) or not DATE_RE.match(value):
            _fail("date must be YYYY-MM-DD")
        try:
            dt.date.fromisoformat(value)
        except ValueError:
            _fail("invalid date")
        lo, hi = cfg.get("min_date"), cfg.get("max_date")
        if lo and value < lo:
            _fail(f"date must be on or after {lo}")
        if hi and value > hi:
            _fail(f"date must be on or before {hi}")
        return {"date": value}

    if t == "email":
        # The address itself never travels through the answer endpoint (CON-3/4).
        if raw.get("provided") is False and len(raw) == 1:
            return {"provided": False}
        _fail("email addresses are submitted through the contact or identity endpoint")

    _fail(f"unsupported question type '{t}'")
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
