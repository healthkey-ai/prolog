"""Facts about the participant, supplied by the host (DEF-14, RUN-23).

A definition may declare ``facts``: named values the host knows about the
participant before a response starts (for example "an earlier result is still
awaited"), each with the values it can take. A ``visible_if`` condition can
then test a fact instead of a question: ``{"fact": "earlier_result", "op": "eq",
"value": "awaited"}``.

The host supplies the values once, when the response is created; they are
stored on the response, so what a participant sees does not change under them.
``resolve_facts`` turns every fact condition into a constant before any other
engine function sees the definition: the rest of the engine knows nothing of
facts, only of ``{"const": true}`` and ``{"const": false}``. A fact the host did
not supply, or supplied with an undeclared value, is unknown, and every
condition on an unknown fact is false (as every condition on an unanswered
question is). Mirrors frontend/src/survey/facts.ts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def declared_facts(definition: dict[str, Any]) -> dict[str, frozenset[str]]:
    """Each declared fact's key and the values it may take."""
    return {f["key"]: frozenset(f["values"]) for f in definition.get("facts") or []}


def known_facts(definition: dict[str, Any], facts: Mapping[str, Any] | None) -> dict[str, str]:
    """The host's facts the definition declares, with a declared value; the rest are unknown."""
    declared = declared_facts(definition)
    return {
        key: value
        for key, value in (facts or {}).items()
        if key in declared and isinstance(value, str) and value in declared[key]
    }


def fact_holds(condition: dict[str, Any], known: Mapping[str, str]) -> bool:
    value = known.get(condition["fact"])
    if value is None:
        return False
    op = condition["op"]
    if op == "eq":
        return value == condition["value"]
    if op == "neq":
        return value != condition["value"]
    if op == "in":
        return value in condition["values"]
    return False


def _resolve(conditions: list[dict[str, Any]], known: Mapping[str, str]) -> list[dict[str, Any]]:
    out = []
    for cond in conditions:
        if "any" in cond:
            out.append(
                {
                    "any": [
                        {"const": fact_holds(c, known)} if "fact" in c else c for c in cond["any"]
                    ]
                }
            )
        elif "fact" in cond:
            out.append({"const": fact_holds(cond, known)})
        else:
            out.append(cond)
    return out


def resolve_facts(definition: dict[str, Any], facts: Mapping[str, Any] | None) -> dict[str, Any]:
    """``definition`` with each fact condition replaced by its truth for
    ``facts``. A definition that declares no facts is returned as it is; any
    other is copied where it changes, never modified in place (it is a shared,
    cached object)."""
    if not definition.get("facts"):
        return definition
    known = known_facts(definition, facts)
    sections = []
    for section in definition["sections"]:
        section = {
            **section,
            "questions": [
                {**q, "visible_if": _resolve(q["visible_if"], known)} if q.get("visible_if") else q
                for q in section["questions"]
            ],
        }
        if section.get("visible_if"):
            section["visible_if"] = _resolve(section["visible_if"], known)
        sections.append(section)
    return {**definition, "sections": sections}
