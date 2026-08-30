"""Visible-question computation over the definition DAG (RUN-7, DEF-10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Answers = dict[str, dict[str, Any]]

ANSWERABLE = {
    "single",
    "dropdown",
    "multi",
    "scale",
    "ranking",
    "matrix",
    "text",
    "number",
    "date",
    "email",
}


@dataclass(frozen=True, slots=True)
class VisibleQuestion:
    key: str
    section_key: str
    section_index: int
    index: int  # position among visible questions
    type: str
    required: bool


def iter_questions(definition: dict[str, Any]):
    for si, section in enumerate(definition["sections"]):
        for q in section["questions"]:
            yield si, section, q


def question_by_key(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {q["key"]: q for _, _, q in iter_questions(definition)}


def is_answered(answer: dict[str, Any] | None) -> bool:
    """True when an answer row exists and carries a value (not a skip)."""
    if not answer or answer.get("skipped"):
        return False
    if "options" in answer:
        return len(answer["options"]) > 0
    if "order" in answer:
        return len(answer["order"]) > 0
    if "ratings" in answer:
        return len(answer["ratings"]) > 0
    if "provided" in answer:
        return bool(answer["provided"])
    return True


def _scalar(answer: dict[str, Any]) -> str | None:
    if "option" in answer:
        return str(answer["option"])
    if "value" in answer:
        return str(answer["value"])
    return None


def evaluate_condition(condition: dict[str, Any], answers: Answers) -> bool:
    """All operators are false when the referenced question is unanswered."""
    answer = answers.get(condition["question"])
    if not is_answered(answer):
        return False
    assert answer is not None
    op = condition["op"]
    if op == "answered":
        return True
    if op == "contains":
        items = answer.get("options") or answer.get("order") or []
        return condition["value"] in items
    scalar = _scalar(answer)
    if scalar is None:
        return False
    if op == "eq":
        return scalar == condition["value"]
    if op == "neq":
        return scalar != condition["value"]
    if op == "in":
        return scalar in condition["values"]
    return False


def conditions_hold(conditions: list[dict[str, Any]], answers: Answers) -> bool:
    return all(evaluate_condition(c, answers) for c in conditions)


def visible_questions(
    definition: dict[str, Any],
    answers: Answers,
    *,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[VisibleQuestion]:
    """One forward pass in presentation order (the DAG's topological order).

    Conditions see only the answers of questions that are themselves visible
    (``seen``): a hidden question's stale answer must not keep anything
    downstream open, otherwise a multi-hop cascade would stop after one hop.

    ``questions`` accepts a caller's precomputed ``question_by_key`` so one
    request does not index the definition several times.
    """
    out: list[VisibleQuestion] = []
    seen: Answers = {}
    if questions is None:
        questions = question_by_key(definition)
    for si, section in enumerate(definition["sections"]):
        if not conditions_hold(section.get("visible_if", []), seen):
            continue
        for q in section["questions"]:
            if not conditions_hold(q.get("visible_if", []), seen):
                continue
            if q["type"] == "matrix" and _dynamic_rows_empty(q, seen, questions):
                continue
            if q["key"] in answers:
                seen[q["key"]] = answers[q["key"]]
            out.append(
                VisibleQuestion(
                    key=q["key"],
                    section_key=section["key"],
                    section_index=si,
                    index=len(out),
                    type=q["type"],
                    required=q.get("required", q["type"] != "info"),
                )
            )
    return out


def _dynamic_rows_empty(
    question: dict[str, Any], answers: Answers, questions: dict[str, dict[str, Any]]
) -> bool:
    """A ``rows_from`` matrix has nothing to ask while its source has no
    selection, so it is hidden rather than left visible with zero rows (which
    could neither be answered nor, under a hard skip policy, skipped)."""
    cfg = question.get("config", {})
    return (
        bool(cfg.get("rows_from"))
        and not cfg.get("rows")
        and not matrix_rows(question, answers, questions)
    )


def visible_keys(
    definition: dict[str, Any],
    answers: Answers,
    *,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    return [v.key for v in visible_questions(definition, answers, questions=questions)]


def matrix_rows(
    question: dict[str, Any], answers: Answers, questions: dict[str, dict[str, Any]]
) -> list[str]:
    """Current row keys of a matrix question: fixed rows or the source selection.

    An ``exclusive`` option of the source ("none of these") is never a row:
    there is nothing to rate about it, so a selection of only exclusive
    options leaves the matrix with no rows (and hidden, see
    ``_dynamic_rows_empty``).
    """
    cfg = question.get("config", {})
    if cfg.get("rows"):
        return [r["key"] for r in cfg["rows"]]
    source_key = cfg.get("rows_from", "")
    source = answers.get(source_key)
    if not is_answered(source):
        return []
    assert source is not None
    source_question = questions.get(source_key) or {}
    exclusive = {o["key"] for o in source_question.get("options", []) if o.get("exclusive")}
    return [k for k in source.get("options", []) if k not in exclusive]
