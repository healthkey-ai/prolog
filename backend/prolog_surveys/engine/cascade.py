"""Invalidation of downstream answers after a change (RUN-16).

Walks the DAG forward implicitly: recomputing visibility over the whole
instrument is a single pass, so we simply recompute and diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .visibility import (
    Answers,
    VisibleQuestion,
    is_answered,
    matrix_rows,
    question_by_key,
    visible_questions,
)


@dataclass
class CascadeResult:
    answers: Answers
    invalidated: list[str] = field(default_factory=list)
    visible: list[str] = field(default_factory=list)
    visible_questions: list[VisibleQuestion] = field(default_factory=list)


def retained_when_hidden(question: dict[str, Any], value: dict[str, Any] | None) -> bool:
    """``{provided: true}`` on an email question records that an address was
    captured (CON-3/4); hiding the question must not throw it away, or
    re-showing it would capture the address twice."""
    return question["type"] == "email" and (value or {}).get("provided") is True


def apply_cascade(
    definition: dict[str, Any],
    answers: Answers,
    *,
    questions: dict[str, dict[str, Any]] | None = None,
) -> CascadeResult:
    """Return the answers that survive, the keys invalidated, and the visible questions."""
    questions = questions or question_by_key(definition)
    surviving: Answers = dict(answers)
    invalidated: set[str] = set()
    # Pruning a matrix can change what is visible (a question conditioned on
    # it being ``answered``), and that can hide further answers, so walk the
    # DAG again until a pass prunes nothing: the forward pass is then a fixed
    # point. Presentation order is topological, so this converges quickly.
    while True:
        visible = visible_questions(definition, surviving, questions=questions)
        visible_set = {v.key for v in visible}

        for key in list(surviving):
            if key not in visible_set and not retained_when_hidden(questions[key], surviving[key]):
                del surviving[key]
                invalidated.add(key)

        pruned = False
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
                invalidated.add(key)
                pruned = True
        if not pruned:
            break

    order = {k: i for i, k in enumerate(questions)}
    return CascadeResult(
        answers=surviving,
        invalidated=sorted(invalidated, key=lambda k: order[k]),
        visible=[v.key for v in visible],
        visible_questions=visible,
    )
