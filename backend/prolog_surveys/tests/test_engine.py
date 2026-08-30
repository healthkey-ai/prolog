"""Phase 2: pure engine against the shared vectors plus targeted unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prolog_surveys.definitions.normalize import normalize
from prolog_surveys.definitions.schema import read_json
from prolog_surveys.engine.answers import AnswerError, validate_answer
from prolog_surveys.engine.cascade import apply_cascade
from prolog_surveys.engine.completion import missing_keys, progress
from prolog_surveys.engine.localize import localize
from prolog_surveys.engine.visibility import (
    evaluate_condition,
    is_answered,
    iter_questions,
    question_by_key,
    visible_keys,
)
from prolog_surveys.options import iso3166
from prolog_surveys.tests.conftest import EXAMPLES_DIR

VECTORS = sorted((EXAMPLES_DIR / "vectors").glob("*.json"))
ISO_KEYS = iso3166.country_keys()


def load_definition(name: str) -> dict:
    return normalize(read_json(EXAMPLES_DIR / name))


def store(definition: dict, answers: dict, key: str, raw: dict) -> dict:
    """Validate + store + cascade, as the API does. Returns the cascade result."""
    questions = question_by_key(definition)
    q = questions[key]
    src = ISO_KEYS if q["type"] == "dropdown" else None
    value = validate_answer(
        q,
        raw,
        answers,
        presentation=definition["presentation"],
        source_options=src,
        questions=questions,
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

    for case in vector.get("retained", []):
        given = dict(case["given"])
        result = store(definition, given, case["answer"]["key"], case["answer"]["value"])
        expect = case["expect"]
        assert result.invalidated == expect["invalidated"]
        assert result.visible == expect["visible"]
        assert given == expect["answers"]
        assert missing_keys(definition, given) == expect["missing"]

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


def test_rows_from_matrix_hidden_until_its_source_has_a_selection():
    """A dynamic-row matrix with zero rows can be neither answered nor (hard
    policy) skipped, so it is not shown at all — even without an explicit
    ``answered`` condition on its source."""
    definition = load_definition("sample-wellbeing.json")
    matrix = question_by_key(definition)["symptom_impact"]
    matrix["visible_if"] = [c for c in matrix["visible_if"] if c["question"] != "symptoms"]
    definition["presentation"]["skip_policy"] = "hard"
    answers: dict = {}
    store(definition, answers, "has_symptoms", {"option": "yes"})
    assert "symptom_impact" not in visible_keys(definition, answers)
    assert "symptom_impact" not in missing_keys(definition, answers)
    store(definition, answers, "symptoms", {"options": ["fatigue"]})
    assert "symptom_impact" in visible_keys(definition, answers)
    store(definition, answers, "symptom_impact", {"ratings": {"fatigue": 3}})
    result = store(definition, answers, "symptoms", {"options": ["none"]})
    # An exclusive option is not a row: nothing to rate, so the matrix hides
    # again and its stale ratings are invalidated.
    assert "symptom_impact" not in visible_keys(definition, answers)
    assert result.invalidated == ["symptom_impact"]
    assert "symptom_impact" not in answers


def test_progress_agrees_with_missing_after_pruning():
    definition = load_definition("sample-wellbeing.json")
    answers: dict = {}
    store(definition, answers, "has_symptoms", {"option": "yes"})
    store(definition, answers, "symptoms", {"options": ["fatigue", "pain"]})
    store(definition, answers, "symptom_impact", {"ratings": {"fatigue": 1, "pain": 2}})
    before = progress(definition, answers)
    # Pruned to {fatigue: 1} while the rows are now [fatigue, sleep]: open again.
    result = store(definition, answers, "symptoms", {"options": ["fatigue", "sleep"]})
    assert result.invalidated == ["symptom_impact"]
    assert "symptom_impact" in missing_keys(definition, answers)
    after = progress(definition, answers)
    assert after["total"] == before["total"]
    assert after["answered"] == before["answered"] - 1
    # A skip is an answer for progress purposes.
    store(definition, answers, "symptom_impact", {"skipped": True})
    assert progress(definition, answers)["answered"] == before["answered"]


def test_cascade_retains_a_hidden_capture_marker():
    definition = load_definition("sample-wellbeing.json")
    for _, _, q in iter_questions(definition):
        if q["type"] == "email":
            q["visible_if"] = [{"question": "has_symptoms", "op": "eq", "value": "yes"}]
    answers = {"has_symptoms": {"option": "yes"}, "contact_email": {"provided": True}}
    result = store(definition, answers, "has_symptoms", {"option": "no"})
    assert result.invalidated == []
    assert answers["contact_email"] == {"provided": True}
    assert "contact_email" not in result.visible
    # A decline is an ordinary answer and goes with the question.
    answers = {"has_symptoms": {"option": "yes"}, "contact_email": {"provided": False}}
    result = store(definition, answers, "has_symptoms", {"option": "no"})
    assert result.invalidated == ["contact_email"]


def test_answer_errors_carry_codes_and_params():
    q = {"key": "t", "type": "text", "text": {"en": "t"}, "config": {"max_length": 6}}
    with pytest.raises(AnswerError) as exc:
        validate_answer(q, {"text": "x" * 7}, {})
    assert exc.value.codes == ["text_too_long"]
    assert exc.value.as_list() == [
        {"code": "text_too_long", "params": {"max": 6}, "message": "text exceeds 6 characters"}
    ]
    assert str(exc.value) == "text exceeds 6 characters"
