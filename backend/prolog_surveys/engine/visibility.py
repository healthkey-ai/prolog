"""Visible-question computation over the definition DAG (RUN-7, DEF-10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Answers = dict[str, dict[str, Any]]

MULTI_VALUED = {"multi", "ranking"}
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


def visible_questions(definition: dict[str, Any], answers: Answers) -> list[VisibleQuestion]:
    """One forward pass in presentation order (the DAG's topological order)."""
    out: list[VisibleQuestion] = []
    for si, section in enumerate(definition["sections"]):
        if not conditions_hold(section.get("visible_if", []), answers):
            continue
        for q in section["questions"]:
            if not conditions_hold(q.get("visible_if", []), answers):
                continue
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


def visible_keys(definition: dict[str, Any], answers: Answers) -> list[str]:
    return [v.key for v in visible_questions(definition, answers)]


def matrix_rows(question: dict[str, Any], answers: Answers) -> list[str]:
    """Current row keys of a matrix question: fixed rows or the source selection."""
    cfg = question.get("config", {})
    if cfg.get("rows"):
        return [r["key"] for r in cfg["rows"]]
    source = answers.get(cfg.get("rows_from", ""))
    if not is_answered(source):
        return []
    assert source is not None
    return list(source.get("options", []))
