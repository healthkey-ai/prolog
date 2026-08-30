"""Invalidation of downstream answers after a change (RUN-16).

Walks the DAG forward implicitly: recomputing visibility over the whole
instrument is a single pass, so we simply recompute and diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .visibility import Answers, is_answered, matrix_rows, question_by_key, visible_keys


@dataclass
class CascadeResult:
    answers: Answers
    invalidated: list[str] = field(default_factory=list)
    visible: list[str] = field(default_factory=list)


def apply_cascade(definition: dict[str, Any], answers: Answers) -> CascadeResult:
    """Return the answers that survive, the keys invalidated, and the visible keys."""
    questions = question_by_key(definition)
    surviving: Answers = dict(answers)
    invalidated: list[str] = []
    visible = visible_keys(definition, surviving)
    visible_set = set(visible)

    for key in list(surviving):
        if key not in visible_set:
            del surviving[key]
            invalidated.append(key)

    for key, value in list(surviving.items()):
        q = questions[key]
        if q["type"] != "matrix" or not is_answered(value):
            continue
        rows = matrix_rows(q, surviving, questions)
        ratings = {r: v for r, v in value.get("ratings", {}).items() if r in rows}
        if ratings != value.get("ratings", {}):
            if ratings:
                surviving[key] = {"ratings": ratings}
            else:
                del surviving[key]
            invalidated.append(key)

    order = {k: i for i, k in enumerate(questions)}
    invalidated.sort(key=lambda k: order[k])
    return CascadeResult(answers=surviving, invalidated=invalidated, visible=visible)
