"""Phase 2: pure engine against the shared vectors plus targeted unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prolog_surveys.definitions.normalize import normalize
from prolog_surveys.engine.answers import AnswerError, validate_answer
from prolog_surveys.engine.cascade import apply_cascade
from prolog_surveys.engine.completion import missing_keys, progress
from prolog_surveys.engine.localize import localize
from prolog_surveys.engine.visibility import (
    evaluate_condition,
    is_answered,
    question_by_key,
    visible_keys,
)
from prolog_surveys.options import iso3166

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = REPO_ROOT / "examples"
VECTORS = sorted((EXAMPLES / "vectors").glob("*.json"))
ISO_KEYS = iso3166.country_keys()


def load_definition(name: str) -> dict:
    return normalize(json.loads((EXAMPLES / name).read_text()))


def store(definition: dict, answers: dict, key: str, raw: dict) -> dict:
    """Validate + store + cascade, as the API does. Returns the cascade result."""
    q = question_by_key(definition)[key]
    src = ISO_KEYS if q["type"] == "dropdown" else None
    value = validate_answer(
        q, raw, answers, presentation=definition["presentation"], source_options=src
    )
    answers[key] = value
    result = apply_cascade(definition, answers)
    answers.clear()
    answers.update(result.answers)
    return result


@pytest.mark.parametrize("vector_path", VECTORS, ids=[p.stem for p in VECTORS])
def test_vector(vector_path: Path):
    vector = json.loads(vector_path.read_text())
    definition = load_definition(vector["definition"])
    answers: dict = {}

    if "initial" in vector:
        assert visible_keys(definition, answers) == vector["initial"]["visible"]

    for step in vector.get("steps", []):
        key = step["answer"]["key"]
        assert key in visible_keys(definition, answers), f"{key} must be visible before answering"
        result = store(definition, answers, key, step["answer"]["value"])
        expect = step.get("expect", {})
        if "invalidated" in expect:
            assert result.invalidated == expect["invalidated"], key
        if "visible" in expect:
            assert result.visible == expect["visible"], key
        if "answers" in expect:
            assert answers == expect["answers"], key
        if "answers_subset" in expect:
            for k, v in expect["answers_subset"].items():
                assert answers[k] == v, key
        if "missing" in expect:
            assert missing_keys(definition, answers) == expect["missing"], key

    for case in vector.get("reject", []):
        answers = dict(case.get("given", {}))
        q = question_by_key(definition)[case["key"]]
        with pytest.raises(AnswerError):
            validate_answer(
                q,
                case["value"],
                answers,
                presentation=definition["presentation"],
                source_options=ISO_KEYS,
            )

    for case in vector.get("accept", []):
        answers = dict(case.get("given", {}))
        q = question_by_key(definition)[case["key"]]
        value = validate_answer(
            q,
            case["value"],
            answers,
            presentation=definition["presentation"],
            source_options=ISO_KEYS,
        )
        if "canonical" in case:
            assert value == case["canonical"]

    if "final" in vector:
        final = vector["final"]
        if "missing" in final:
            assert missing_keys(definition, answers) == final["missing"]
        if "progress" in final:
            assert progress(definition, answers) == final["progress"]


# --- unit tests ----------------------------------------------------------------


def test_is_answered():
    assert not is_answered(None)
    assert not is_answered({"skipped": True})
    assert not is_answered({"options": []})
    assert is_answered({"options": ["a"]})
    assert not is_answered({"provided": False})
    assert is_answered({"provided": True})
    assert is_answered({"value": 0})


def test_conditions_false_when_unanswered():
    cond = {"question": "q", "op": "neq", "value": "x"}
    assert evaluate_condition(cond, {}) is False
    assert evaluate_condition(cond, {"q": {"skipped": True}}) is False
    assert evaluate_condition(cond, {"q": {"option": "y"}}) is True
    assert evaluate_condition(
        {"question": "q", "op": "in", "values": ["1", "2"]}, {"q": {"value": 2}}
    )
    assert evaluate_condition(
        {"question": "q", "op": "contains", "value": "b"}, {"q": {"order": ["a", "b"]}}
    )


def test_hard_skip_policy_blocks_required():
    definition = load_definition("sample-wellbeing.json")
    q = question_by_key(definition)["age_band"]
    with pytest.raises(AnswerError):
        validate_answer(q, {"skipped": True}, {}, presentation={"skip_policy": "hard"})
    optional = question_by_key(definition)["anything_else"]
    assert validate_answer(
        optional, {"skipped": True}, {}, presentation={"skip_policy": "hard"}
    ) == {"skipped": True}


def test_skip_shape_is_strict():
    definition = load_definition("sample-wellbeing.json")
    q = question_by_key(definition)["age_band"]
    with pytest.raises(AnswerError):
        validate_answer(q, {"skipped": True, "option": "30_49"}, {})


def test_localize_picks_language_with_fallback():
    definition = load_definition("sample-wellbeing.json")
    definition["sections"][0]["title"].pop("fr")
    fr = localize(definition, "fr")
    assert fr["title"] == "Bilan de bien-être"
    assert fr["sections"][0]["title"] == "About you"  # fallback to default
    assert "notes" not in fr
    q = question_by_key(fr)["symptom_impact"]
    assert q["config"]["scale"]["point_labels"][0] == "Pas du tout"
    assert question_by_key(fr)["symptoms"]["options"][0]["label"] == "Fatigue"
    assert localize(definition, "xx")["language"] == "en"


def test_iso3166_source_localised():
    en = iso3166.countries("en")
    es = iso3166.countries("es")
    assert {"key": "GB", "label": "United Kingdom"} in en
    assert any(c["key"] == "DE" and c["label"].startswith("Alemania") for c in es)
    assert "GB" in iso3166.country_keys()


def test_multi_hop_cascade_reaches_dependants_of_hidden_answers():
    """q1 gates q2; q2's answer gates q3. A hidden q2 must not keep q3 open."""
    chain = {
        "sections": [
            {
                "key": "s",
                "questions": [
                    {"key": "q1", "type": "single", "options": [{"key": "yes"}, {"key": "no"}]},
                    {
                        "key": "q2",
                        "type": "single",
                        "options": [{"key": "a"}, {"key": "b"}],
                        "visible_if": [{"question": "q1", "op": "eq", "value": "yes"}],
                    },
                    {
                        "key": "q3",
                        "type": "text",
                        "visible_if": [{"question": "q2", "op": "eq", "value": "a"}],
                    },
                ],
            }
        ]
    }
    answers = {"q1": {"option": "no"}, "q2": {"option": "a"}, "q3": {"text": "hello"}}
    assert visible_keys(chain, answers) == ["q1"]
    result = apply_cascade(chain, answers)
    assert result.invalidated == ["q2", "q3"]
    assert list(result.answers) == ["q1"]
    assert result.visible == ["q1"]
