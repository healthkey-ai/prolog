"""Completion rule (RUN-18): every visible answerable question has an answer row."""

from __future__ import annotations

from typing import Any

from .visibility import (
    ANSWERABLE,
    Answers,
    VisibleQuestion,
    is_answered,
    matrix_rows,
    question_by_key,
    visible_questions,
)


def missing_keys(
    definition: dict[str, Any],
    answers: Answers,
    *,
    visible: list[VisibleQuestion] | None = None,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Visible answerable questions without a complete answer row.

    ``visible``/``questions`` accept a caller's precomputed walk so one request
    does not traverse the definition several times.
    """
    if questions is None:
        questions = question_by_key(definition)
    if visible is None:
        visible = visible_questions(definition, answers, questions=questions)
    missing: list[str] = []
    for v in visible:
        if v.type not in ANSWERABLE:
            continue
        value = answers.get(v.key)
        if value is None:
            missing.append(v.key)
            continue
        q = questions[v.key]
        if q["type"] == "matrix" and is_answered(value):
            rows = matrix_rows(q, answers, questions)
            if set(value.get("ratings", {})) != set(rows):
                missing.append(v.key)
    return missing


def progress(
    definition: dict[str, Any],
    answers: Answers,
    *,
    visible: list[VisibleQuestion] | None = None,
    missing: list[str] | None = None,
    questions: dict[str, dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Answered = visible answerable questions that are not missing, so a
    pruned matrix (rated, but not for every current row) counts as open,
    exactly as ``missing_keys`` reports it; a skip counts as answered."""
    if visible is None:
        visible = visible_questions(definition, answers, questions=questions)
    if missing is None:
        missing = missing_keys(definition, answers, visible=visible, questions=questions)
    total = sum(1 for v in visible if v.type in ANSWERABLE)
    return {"answered": total - len(missing), "total": total}
