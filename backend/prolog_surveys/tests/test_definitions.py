"""Phase 1: schema + semantic validation, DAG rule, loader, activation."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.definitions.loader import (
    ActivationError,
    DefinitionError,
    activate_version,
    load_definition,
    validate_definition,
)
from prolog_surveys.definitions.normalize import checksum, normalize
from prolog_surveys.definitions.validate import build_graph, has_errors, validate_semantics
from prolog_surveys.models import LifecycleStatus, SurveyQuestion, SurveyVersion

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = REPO_ROOT / "examples" / "sample-wellbeing.json"


@pytest.fixture
def example() -> dict:
    return json.loads(EXAMPLE.read_text())


def question(doc: dict, key: str) -> dict:
    for s in doc["sections"]:
        for q in s["questions"]:
            if q["key"] == key:
                return q
    raise KeyError(key)


def codes(issues, level="error"):
    return sorted({i.code for i in issues if i.level == level})


# --- example instrument -----------------------------------------------------


def test_example_is_valid(example):
    issues = validate_definition(example)
    assert not has_errors(issues), [str(i) for i in issues]
    assert codes(issues, "warning") == []


def test_example_graph_edges_point_backward(example):
    g = build_graph(example)
    for source, deps in g.edges.items():
        for dep in deps:
            assert g.index[dep] < g.index[source]
    assert g.edges["symptom_impact"] == {"has_symptoms", "symptoms"}
    assert g.dependents["has_symptoms"] >= {"symptoms", "symptom_impact", "told_clinician"}


# --- structural ----------------------------------------------------------------


def test_schema_error_reported_with_path(example):
    example["sections"][0]["questions"][1]["type"] = "checkbox"
    issues = validate_definition(example)
    assert issues[0].code == "schema"
    assert "type" in issues[0].path


def test_schema_rejects_both_email_modes(example):
    question(example, "contact_email")["config"]["link_identity"] = True
    assert has_errors(validate_definition(example))


# --- semantic rules ------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (
            lambda d: d["sections"][0]["questions"].append(copy.deepcopy(question(d, "age_band"))),
            "duplicate_key",
        ),
        (
            lambda d: d["sections"].append(
                copy.deepcopy(d["sections"][0])
                | {"questions": [{"key": "x", "type": "info", "text": {"en": "x"}}]}
            ),
            "duplicate_key",
        ),
        (
            lambda d: question(d, "symptoms")["options"].append(
                {"key": "pain", "label": {"en": "dup"}}
            ),
            "duplicate_key",
        ),
        (lambda d: question(d, "symptoms")["config"].update(max_selections=99), "max_selections"),
        (
            lambda d: question(d, "symptoms")["config"].update(min_selections=3, max_selections=2),
            "min_selections",
        ),
        (
            lambda d: question(d, "outcome_ranking")["config"].update(optional_items=["nope"]),
            "optional_items",
        ),
        (lambda d: question(d, "overall")["config"]["scale"].update(min=5, max=1), "scale_range"),
        (
            lambda d: question(d, "symptom_impact")["config"]["scale"]["point_labels"].pop(),
            "scale_labels",
        ),
        (
            lambda d: question(d, "daily_activities")["config"].update(rows_from="symptoms"),
            "matrix_rows",
        ),
        (
            lambda d: d["sections"][-1]["questions"].append(
                {"key": "e2", "type": "email", "text": {"en": "x"}}
            ),
            "email_count",
        ),
        (
            lambda d: question(d, "contact_email").update(config={"link_identity": True}),
            "link_identity",
        ),
        (lambda d: d["translation_status"].pop("fr"), "translation_status"),
        (lambda d: d["translation_status"].update(de="reviewed"), "translation_status"),
        (lambda d: d.update(default_language="de"), "default_language"),
        (lambda d: question(d, "overall")["text"].pop("en"), "i18n_default"),
        (lambda d: question(d, "birth_year")["config"].update(min_value=3000), "number_range"),
        (lambda d: question(d, "last_visit")["config"].update(min_date="2030-01-01"), "date_range"),
        (lambda d: d.update(schema_version=2), "schema_version"),
    ],
)
def test_semantic_errors(example, mutate, expected):
    mutate(example)
    issues = validate_definition(example)
    assert expected in codes(issues), [str(i) for i in issues]


@pytest.mark.parametrize(
    "mutate, expected",
    [
        # forward reference: symptoms depends on a later question
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "support_wanted", "op": "contains", "value": "peer"}
            ),
            "dag_forward",
        ),
        # self reference
        (
            lambda d: question(d, "has_symptoms").update(
                visible_if=[{"question": "has_symptoms", "op": "eq", "value": "yes"}]
            ),
            "dag_self",
        ),
        # unknown reference
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "ghost", "op": "answered"}
            ),
            "dag_unknown",
        ),
        # rows_from pointing forward
        (
            lambda d: question(d, "symptom_impact")["config"].update(rows_from="support_wanted"),
            "dag_forward",
        ),
        # rows_from must be multi
        (
            lambda d: question(d, "symptom_impact")["config"].update(rows_from="has_symptoms"),
            "rows_from_type",
        ),
        # section gate on a question in the same section
        (
            lambda d: d["sections"][1].update(
                visible_if=[{"question": "overall", "op": "eq", "value": "5"}]
            ),
            "dag_section",
        ),
    ],
)
def test_dag_rule(example, mutate, expected):
    mutate(example)
    assert expected in codes(validate_semantics(example))


def test_cycle_is_impossible_because_edges_only_point_backward(example):
    # A "cycle" can only be expressed with at least one forward edge, which is rejected.
    question(example, "has_symptoms")["visible_if"] = [
        {"question": "symptoms", "op": "contains", "value": "pain"}
    ]
    issues = validate_semantics(example)
    assert "dag_forward" in codes(issues)


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "has_symptoms", "op": "eq", "value": "maybe"}
            ),
            "condition_value",
        ),
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "overall", "op": "eq", "value": "9"}
            ),
            "condition_value",
        ),
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "has_symptoms", "op": "contains", "value": "yes"}
            ),
            "condition_op",
        ),
        (
            lambda d: question(d, "symptom_impact")["visible_if"].append(
                {"question": "symptoms", "op": "eq", "value": "pain"}
            ),
            "condition_op",
        ),
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "welcome", "op": "answered"}
            ),
            "condition_op",
        ),
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "birth_year", "op": "eq", "value": "1"}
            ),
            "condition_op",
        ),
    ],
)
def test_condition_rules(example, mutate, expected):
    mutate(example)
    assert expected in codes(validate_semantics(example))


def test_dropdown_with_source_accepts_any_value(example):
    question(example, "age_band")["visible_if"] = [
        {"question": "country", "op": "eq", "value": "GB"}
    ]
    assert "condition_value" not in codes(validate_semantics(example))


def test_unreachable_question_warned(example):
    question(example, "symptoms")["visible_if"].append(
        {"question": "has_symptoms", "op": "eq", "value": "no"}
    )
    issues = validate_semantics(example)
    assert not has_errors(issues)
    unreachable = [i.message for i in issues if i.code == "unreachable"]
    assert any("'symptoms'" in m for m in unreachable)
    # dependents of an unreachable question are unreachable too
    assert len(unreachable) >= 2


def test_config_mismatch_is_warning(example):
    question(example, "overall")["config"]["max_selections"] = 2
    issues = validate_semantics(example)
    assert not has_errors(issues)
    assert "config_mismatch" in codes(issues, "warning")


# --- normalisation --------------------------------------------------------------


def test_normalize_fills_defaults_and_is_deterministic(example):
    doc = normalize(example)
    assert doc["presentation"]["skip_policy"] == "soft"
    assert doc["participation"] == {"anonymous": True, "resume": "browser_token"}
    q = question(doc, "symptoms")
    assert q["required"] is True and q["config"]["min_selections"] == 1
    assert question(doc, "welcome")["required"] is False
    assert question(doc, "anything_else")["config"]["multiline"] is True
    assert "$schema" not in doc
    assert checksum(doc) == checksum(normalize(example))


# --- loader ---------------------------------------------------------------------


@pytest.mark.django_db
def test_load_is_idempotent(example):
    first = load_definition(example, source="x.json")
    second = load_definition(example, source="x.json")
    assert first.created and not second.created and not second.changed
    assert SurveyVersion.objects.count() == 1
    assert first.version.status == LifecycleStatus.DRAFT
    assert first.version.survey.allow_anonymous_participation is True
    assert first.version.survey.theme_code == "default"


@pytest.mark.django_db
def test_draft_can_change_published_cannot(example):
    result = load_definition(example)
    example["title"]["en"] = "Changed"
    assert load_definition(example).changed
    # make it reviewed and activate
    example["translation_status"]["fr"] = "reviewed"
    load_definition(example, activate=True)
    example["title"]["en"] = "Changed again"
    with pytest.raises(DefinitionError) as exc:
        load_definition(example)
    assert "immutable" in [i.code for i in exc.value.issues]
    assert SurveyVersion.objects.get(pk=result.version.pk).definition["title"]["en"] == "Changed"


@pytest.mark.django_db
def test_activation_refused_while_machine_translated(example):
    version = load_definition(example).version
    with pytest.raises(ActivationError, match="fr"):
        activate_version(version)
    assert SurveyVersion.objects.get(pk=version.pk).status == LifecycleStatus.DRAFT


@pytest.mark.django_db
def test_activation_archives_previous_and_materializes(example):
    example["translation_status"]["fr"] = "reviewed"
    v1 = load_definition(example, activate=True).version
    assert v1.status == LifecycleStatus.ACTIVE
    keys = list(SurveyQuestion.objects.filter(survey_version=v1).values_list("key", flat=True))
    assert keys[:3] == ["welcome", "country", "age_band"]
    assert SurveyQuestion.objects.get(survey_version=v1, key="symptoms").options.count() == 6

    example["version"] = "1.1"
    v2 = load_definition(example, activate=True).version
    v1.refresh_from_db()
    assert v1.status == LifecycleStatus.ARCHIVED and v1.archived_at is not None
    assert v2.status == LifecycleStatus.ACTIVE
    assert v1.survey.active_version == v2
    with pytest.raises(ActivationError):
        activate_version(v1)


@pytest.mark.django_db
def test_invalid_definition_is_rejected(example):
    question(example, "symptoms")["visible_if"].append({"question": "ghost", "op": "answered"})
    with pytest.raises(DefinitionError):
        load_definition(example)
    assert SurveyVersion.objects.count() == 0


# --- management commands ------------------------------------------------------


def test_validate_command_ok(capsys):
    call_command("validate_definition", str(EXAMPLE))
    assert "OK" in capsys.readouterr().out


def test_validate_command_fails(tmp_path, example):
    question(example, "symptoms")["visible_if"].append({"question": "ghost", "op": "answered"})
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(example))
    with pytest.raises(CommandError):
        call_command("validate_definition", str(bad))


@pytest.mark.django_db
def test_load_command_and_startup_loader(tmp_path, example, settings, capsys):
    (tmp_path / "a.json").write_text(json.dumps(example))
    call_command("load_definition", str(tmp_path))
    assert "created" in capsys.readouterr().out
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    call_command("load_definitions")
    assert "unchanged" in capsys.readouterr().out
    with pytest.raises(CommandError):
        call_command("load_definition", str(tmp_path), "--activate")  # fr is machine
