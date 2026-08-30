"""Completion rule (RUN-18): every visible answerable question has an answer row."""

from __future__ import annotations

from typing import Any

from .visibility import (
    ANSWERABLE,
    Answers,
    is_answered,
    matrix_rows,
    question_by_key,
    visible_questions,
)


def missing_keys(definition: dict[str, Any], answers: Answers) -> list[str]:
    questions = question_by_key(definition)
    missing: list[str] = []
    for v in visible_questions(definition, answers):
        if v.type not in ANSWERABLE:
            continue
        value = answers.get(v.key)
        if value is None:
            missing.append(v.key)
            continue
        q = questions[v.key]
        if q["type"] == "matrix" and is_answered(value):
            rows = matrix_rows(q, answers)
            if set(value.get("ratings", {})) != set(rows):
                missing.append(v.key)
    return missing


def progress(definition: dict[str, Any], answers: Answers) -> dict[str, int]:
    visible = [v for v in visible_questions(definition, answers) if v.type in ANSWERABLE]
    answered = sum(1 for v in visible if v.key in answers)
    return {"answered": answered, "total": len(visible)}
