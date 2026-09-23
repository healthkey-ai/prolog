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
    if op in ("contains", "not_contains"):
        items = answer.get("options") or answer.get("order") or []
        # Both false until answered (above): not_contains means "answered, and
        # without this option" — a gate that opens on an answer, never on silence.
        return (condition["value"] in items) == (op == "contains")
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
            if _dynamic_rows_empty(q, seen, questions):
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
    """A question whose rows or options come from an earlier selection has
    nothing to ask while that selection is empty, so it is hidden rather than
    left visible with nothing in it (which could neither be answered nor,
    under a hard skip policy, skipped).

    For ``options_from`` the question's own options do not count: an instrument
    that offers "I am not sure" beside the sourced ones is not asking anything
    when the source contributed none.
    """
    cfg = question.get("config", {})
    if cfg.get("rows_from") and not cfg.get("rows"):
        return not matrix_rows(question, answers, questions)
    if cfg.get("options_from"):
        return not sourced_option_keys(question, answers, questions)
    return False


def dynamic_source(question: dict[str, Any]) -> str | None:
    """The earlier question this one takes its rows or options from, if any."""
    cfg = question.get("config", {})
    return cfg.get("options_from") or (cfg.get("rows_from") if not cfg.get("rows") else None)


def pending_keys(
    definition: dict[str, Any],
    answers: Answers,
    *,
    visible: list[VisibleQuestion] | None = None,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Hidden answerable questions that may still appear.

    A hidden question is *closed* — it will not be asked — when something it
    depends on has been decided against it: a gating question that holds a row
    (a value or a skip) with which the condition is false, or a gate that is
    itself closed. It is *pending* while every false condition rests on a
    question the respondent has simply not reached yet. The distinction is
    what lets a progress count treat a skipped branch as passed and an
    unreached one as still to come. Mirrors visibility.ts.
    """
    if questions is None:
        questions = question_by_key(definition)
    if visible is None:
        visible = visible_questions(definition, answers, questions=questions)
    shown = {v.key for v in visible}
    # Conditions are judged on visible answers only, as visible_questions
    # does: a hidden gate's stale answer settles nothing.
    seen = {k: v for k, v in answers.items() if k in shown}
    closed: set[str] = set()
    pending: list[str] = []

    def settled(key: str) -> bool:
        # A visible question is settled once it holds any row; a hidden one
        # once it is closed. Anything else is still ahead of the respondent.
        return key in answers if key in shown else key in closed

    for _, section, q in iter_questions(definition):
        if q["key"] in shown:
            continue
        conditions = [*section.get("visible_if", []), *q.get("visible_if", [])]
        false = [c for c in conditions if not evaluate_condition(c, seen)]
        # A question hidden for want of rows or options waits on its source the
        # same way a condition waits on its question.
        if not false:
            source = dynamic_source(q)
            if source:
                false = [{"question": source}]
        if any(settled(c["question"]) for c in false):
            closed.add(q["key"])
        elif q["type"] in ANSWERABLE:
            pending.append(q["key"])
    return pending


def visible_keys(
    definition: dict[str, Any],
    answers: Answers,
    *,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    return [v.key for v in visible_questions(definition, answers, questions=questions)]


def selected_from(
    source_key: str, answers: Answers, questions: dict[str, dict[str, Any]]
) -> list[str]:
    """What an earlier ``multi`` selected, in its own option order, without its
    ``exclusive`` options.

    An exclusive option is "none of these" or "I am not sure": there is nothing
    to rate about it and nothing to single out from it, so a selection of only
    exclusive options contributes nothing — which is what leaves the dependent
    question hidden (see ``_dynamic_rows_empty``).
    """
    source = answers.get(source_key)
    if not is_answered(source):
        return []
    assert source is not None
    source_question = questions.get(source_key) or {}
    exclusive = {o["key"] for o in source_question.get("options", []) if o.get("exclusive")}
    return [k for k in source.get("options", []) if k not in exclusive]


def matrix_rows(
    question: dict[str, Any], answers: Answers, questions: dict[str, dict[str, Any]]
) -> list[str]:
    """Current row keys of a matrix question: fixed rows or the source selection."""
    cfg = question.get("config", {})
    if cfg.get("rows"):
        return [r["key"] for r in cfg["rows"]]
    return selected_from(cfg.get("rows_from", ""), answers, questions)


def sourced_option_keys(
    question: dict[str, Any], answers: Answers, questions: dict[str, dict[str, Any]]
) -> list[str]:
    """Option keys an ``options_from`` question takes from its source (DEF-11)."""
    cfg = question.get("config", {})
    if not cfg.get("options_from"):
        return []
    return selected_from(cfg["options_from"], answers, questions)


def offered_option_keys(
    question: dict[str, Any], answers: Answers, questions: dict[str, dict[str, Any]]
) -> list[str]:
    """Every option key a question offers now: what its source contributes
    first, then its own, and never the same key twice — an instrument whose
    source already offers "I am not sure" must not show it a second time."""
    sourced = sourced_option_keys(question, answers, questions)
    own = [o["key"] for o in question.get("options", [])]
    return sourced + [k for k in own if k not in set(sourced)]
