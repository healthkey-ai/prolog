"""Phase 1: schema + semantic validation, DAG rule, loader, activation."""

from __future__ import annotations

import copy
import json
import re

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from prolog_surveys.definitions import loader
from prolog_surveys.definitions.loader import (
    ActivationError,
    DefinitionError,
    activate_version,
    load_definition,
    validate_definition,
)
from prolog_surveys.definitions.normalize import checksum, normalize, source_checksum
from prolog_surveys.definitions.validate import has_errors, validate_semantics, walk_i18n
from prolog_surveys.engine.localize import I18N_FIELDS, localize
from prolog_surveys.models import LifecycleStatus, SurveyQuestion, SurveyVersion
from prolog_surveys.tests.conftest import EXAMPLE_PATH


def question(doc: dict, key: str) -> dict:
    for s in doc["sections"]:
        for q in s["questions"]:
            if q["key"] == key:
                return q
    raise KeyError(key)


def codes(issues, level="error"):
    return sorted({i.code for i in issues if i.level == level})


# --- example instrument -----------------------------------------------------


def test_priority_orders_without_restricting(example):
    """A pinned list is accepted, and leaves every option answerable.

    Ordering and restriction are separate keys on purpose: pinning three
    countries must not quietly make the other two hundred unanswerable.
    """
    from prolog_surveys.engine.answers import source_keys

    cfg = question(example, "country")["config"]
    cfg.update(options_source_priority=["DE", "FR"])

    assert not has_errors(validate_definition(example, profile="standalone"))
    assert source_keys(cfg, {"DE", "FR", "GB", "US"}) == {"DE", "FR", "GB", "US"}


def test_example_is_valid(example):
    issues = validate_definition(example)
    assert not has_errors(issues), [str(i) for i in issues]
    assert codes(issues, "warning") == []


def test_section_mode_is_rejected_until_implemented(example):
    example["presentation"] = {"mode": "section"}
    issues = validate_semantics(example)
    assert codes(issues, "error") == ["presentation_mode"]
    example["presentation"] = {"mode": "question"}
    assert not has_errors(validate_semantics(example))


# --- structural ----------------------------------------------------------------


def test_schema_error_reported_with_path(example):
    example["sections"][0]["questions"][1]["type"] = "checkbox"
    issues = validate_definition(example)
    assert issues[0].code == "schema"
    assert "type" in issues[0].path


def test_schema_rejects_both_email_modes(example):
    question(example, "contact_email")["config"]["link_identity"] = True
    assert has_errors(validate_definition(example))


@pytest.mark.parametrize(
    "mutate, path",
    [
        # Lengths mirror the database columns (Survey.slug, SurveyVersion.version, ...)
        # so a definition the schema admits can always be stored.
        (lambda d: d.update(slug="s" * 121), "$.slug"),
        (lambda d: d.update(version="1." + "1" * 31), "$.version"),
        (lambda d: d.update(theme="t" * 65), "$.theme"),
        (lambda d: d["sections"][0].update(key="k" * 129), "$.sections[0].key"),
        (lambda d: question(d, "overall").update(key="k" * 129), "$.sections[1].questions[0].key"),
        (
            lambda d: question(d, "symptoms")["options"][0].update(key="k" * 129),
            "$.sections[1].questions[3].options[0].key",
        ),
        (
            lambda d: d.update(consent={"version": "v" * 65, "text": {"en": "x"}}),
            "$.consent.version",
        ),
    ],
)
def test_schema_bounds_identifier_lengths(example, mutate, path):
    mutate(example)
    issues = validate_definition(example)
    assert [i.path for i in issues if i.code == "schema"] == [path], [str(i) for i in issues]


def _repeat(**overrides):
    return {"every": 1, "unit": "weeks", "start_date": "2026-01-01", **overrides}


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
        (lambda d: question(d, "symptoms")["config"].update(min_selections=99), "min_selections"),
        (lambda d: question(d, "contact_email")["config"].pop("store_separately"), "email_capture"),
        (
            lambda d: question(d, "symptoms")["config"].update(min_selections=3, max_selections=2),
            "min_selections",
        ),
        (
            lambda d: question(d, "outcome_ranking")["config"].update(optional_items=["nope"]),
            "optional_items",
        ),
        # every item optional: {"order": []} would validate yet never count as answered
        (
            lambda d: question(d, "outcome_ranking")["config"].update(
                optional_items=[o["key"] for o in question(d, "outcome_ranking")["options"]]
            ),
            "optional_items",
        ),
        (lambda d: question(d, "overall")["config"]["scale"].update(min=5, max=1), "scale_range"),
        # the runner renders one control per point; a typo must not hang the page
        (
            lambda d: question(d, "overall")["config"]["scale"].update(min=0, max=10_000_000),
            "scale_range",
        ),
        # a typo in the include list would silently shrink the offered options
        (
            lambda d: question(d, "country")["config"].update(options_source_include=["DE", "XX"]),
            "options_source_include",
        ),
        (  # without options_source there is nothing to restrict
            lambda d: question(d, "age_band").__setitem__(
                "config", {"options_source_include": ["DE"]}
            ),
            "options_source_include",
        ),
        # a typo in the priority list pins nothing, and nobody notices in review
        (
            lambda d: question(d, "country")["config"].update(options_source_priority=["XX"]),
            "options_source_priority",
        ),
        (  # without options_source there is nothing to order
            lambda d: question(d, "age_band").__setitem__(
                "config", {"options_source_priority": ["DE"]}
            ),
            "options_source_priority",
        ),
        (  # pinning what the include list leaves out asks for an option nobody can pick
            lambda d: question(d, "country")["config"].update(
                options_source_include=["DE", "FR"], options_source_priority=["GB"]
            ),
            "options_source_priority",
        ),
        # the runner renders privacy_url as a link: only absolute http(s) URLs
        (
            lambda d: d.setdefault("consent", {"version": "1", "text": {"en": "x"}}).update(
                privacy_url="javascript:alert(1)"
            ),
            "schema",
        ),
        (
            lambda d: d.setdefault("consent", {"version": "1", "text": {"en": "x"}}).update(
                privacy_url="/privacy"
            ),
            "schema",
        ),
        (  # passes the schema pattern but has no host
            lambda d: d.setdefault("consent", {"version": "1", "text": {"en": "x"}}).update(
                privacy_url="http://?x"
            ),
            "privacy_url",
        ),
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
        (lambda d: question(d, "last_visit")["config"].update(min_date="2100-01-01"), "date_range"),
        # the schema only checks the digit pattern; February 30th gets this far
        (
            lambda d: question(d, "last_visit")["config"].update(max_date="2026-02-30"),
            "date_invalid",
        ),
        (lambda d: d.update(schema_version=2), "schema_version"),
        (lambda d: d["title"].update(en="t" * 256), "title_length"),
        (
            lambda d: d.update(
                participation={"anonymous": False, "repeat": _repeat(start_date="2026-02-30")}
            ),
            "repeat_date_invalid",
        ),
        (
            lambda d: d.update(
                participation={"anonymous": False, "repeat": _repeat(end_date="2026-00-10")}
            ),
            "repeat_date_invalid",
        ),
        (
            lambda d: d.update(
                participation={"anonymous": False, "repeat": _repeat(end_date="2025-12-31")}
            ),
            "repeat_range",
        ),
    ],
)
def test_semantic_errors(example, mutate, expected):
    mutate(example)
    issues = validate_definition(example, profile="standalone")
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
        # The engine compares str(answer) == value: only the canonical spelling can match.
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "overall", "op": "eq", "value": "03"}
            ),
            "condition_value",
        ),
        (
            lambda d: question(d, "symptoms")["visible_if"].append(
                {"question": "overall", "op": "in", "values": ["3", "-0"]}
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


def test_repeat_on_anonymous_survey_is_warned(example):
    # RUN-5: repeat administration reaches invited participants only, so the
    # schedule is inert (the scheduler skips anonymous surveys) but not fatal.
    example["participation"] = {"anonymous": True, "repeat": _repeat(end_date="2026-06-01")}
    issues = validate_semantics(example)
    assert not has_errors(issues)
    assert [i.path for i in issues if i.code == "repeat_anonymous"] == ["$.participation.repeat"]
    example["participation"]["anonymous"] = False
    assert codes(validate_semantics(example), "warning") == []


def test_title_length_is_checked_in_the_default_language_only(example):
    example["title"]["es"] = "t" * 300  # only title[default_language] is stored on Survey
    assert "title_length" not in codes(validate_semantics(example))


# --- i18n inventory: validator vs localiser -------------------------------------


def _resolve(doc, path: str):
    node = doc
    for key, index in re.findall(r"\.([a-z_]+)|\[(\d+)\]", path):
        node = node[int(index)] if index else node[key]
    return node


def test_i18n_walk_matches_localizer(example):
    """The validator's i18n inventory (``walk_i18n``) and the engine's
    ``I18N_FIELDS`` are maintained separately; a field one knows and the other
    does not would validate yet reach the runner as a ``{lang: text}`` object
    (or be localised without its default-language check)."""
    example["consent"] = {"version": "1", "text": {"en": "Consent", "es": "Consentimiento"}}
    walked = walk_i18n(example)
    # every field name the localiser localises occurs in the walk (the example
    # exercises them all), and every walked path is a language map
    assert I18N_FIELDS <= {re.split(r"[.\[]", path)[-1] for path, _ in walked}
    for path, obj in walked:
        assert obj and set(obj) <= set(example["languages"]), path
    # after localisation every walked path is a plain string...
    localized = localize(example, "es")
    for path, _ in walked:
        assert isinstance(_resolve(localized, path), str), path
    # ...and no language map survives anywhere the walk did not look
    survivors: list[str] = []

    def scan(node, path):
        if isinstance(node, dict):
            if path != "$.translation_status" and example["default_language"] in node:
                survivors.append(path)
            for k, v in node.items():
                scan(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                scan(v, f"{path}[{i}]")

    scan(localized, "$")
    assert survivors == []


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


def test_scale_span_bound_allows_a_wide_but_sane_scale(example):
    question(example, "overall")["config"]["scale"].update(min=0, max=100)
    assert "scale_range" not in codes(validate_definition(example))


@pytest.mark.django_db
def test_unchanged_file_reloads_after_a_normaliser_change(example, monkeypatch):
    """The checksum identifies the authored document, not the normalised one:
    a new engine default must not make every unchanged active survey fail to
    load at container start ("immutable"), and the stored version picks the
    default up so the engine never reads a document missing it."""
    load_definition(example, activate=True)
    original = normalize

    def newer_normalize(doc):
        out = original(doc)
        out["presentation"]["new_default"] = True
        return out

    monkeypatch.setattr(loader, "normalize", newer_normalize)
    result = load_definition(example)
    assert not result.changed and not result.created
    version = SurveyVersion.objects.get(pk=result.version.pk)
    assert version.status == LifecycleStatus.ACTIVE
    assert version.definition["presentation"]["new_default"] is True
    assert version.checksum == source_checksum(example)
    # An edit to the source is still a change, and still refused once published.
    example["title"]["en"] = "Changed"
    with pytest.raises(DefinitionError):
        load_definition(example)


@pytest.mark.django_db
def test_version_stored_with_legacy_normalised_checksum_reloads(example):
    """Rows written before the checksum moved to the source document carry
    ``checksum(normalize(doc))``; an unchanged file must still re-load and
    migrate the digest instead of refusing the active version as edited."""
    version = load_definition(example, activate=True).version
    SurveyVersion.objects.filter(pk=version.pk).update(checksum=checksum(normalize(example)))
    result = load_definition(example)
    assert not result.changed and not result.created
    version.refresh_from_db()
    assert version.status == LifecycleStatus.ACTIVE
    assert version.checksum == source_checksum(example)
    assert not load_definition(example).changed  # migrated: the plain path from now on


def test_source_checksum_ignores_schema_pointer_only(example):
    with_pointer = {**example, "$schema": "../elsewhere/schema.json"}
    assert source_checksum(with_pointer) == source_checksum(example)
    assert source_checksum({**example, "version": "1.1"}) != source_checksum(example)


@pytest.mark.django_db
def test_draft_can_change_published_cannot(example):
    result = load_definition(example)
    example["title"]["en"] = "Changed"
    assert load_definition(example).changed
    load_definition(example, activate=True)
    example["title"]["en"] = "Changed again"
    with pytest.raises(DefinitionError) as exc:
        load_definition(example)
    assert "immutable" in [i.code for i in exc.value.issues]
    assert SurveyVersion.objects.get(pk=result.version.pk).definition["title"]["en"] == "Changed"


@pytest.mark.django_db
def test_activation_refused_while_machine_translated(example):
    example["translation_status"]["fr"] = "machine"
    version = load_definition(example).version
    with pytest.raises(ActivationError, match="fr"):
        activate_version(version)
    assert SurveyVersion.objects.get(pk=version.pk).status == LifecycleStatus.DRAFT


@pytest.mark.django_db
def test_allow_unreviewed_override_logs(example, caplog):
    example["translation_status"]["fr"] = "machine"
    version = load_definition(example).version
    with pytest.raises(ActivationError):
        activate_version(version)
    activate_version(version, allow_unreviewed=True)
    assert SurveyVersion.objects.get(pk=version.pk).status == LifecycleStatus.ACTIVE
    assert "UNREVIEWED" in caplog.text


@pytest.mark.django_db
def test_activation_archives_previous_and_materializes(example):
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
    call_command("validate_definition", str(EXAMPLE_PATH))
    assert "OK" in capsys.readouterr().out


def test_validate_command_fails(tmp_path, example):
    question(example, "symptoms")["visible_if"].append({"question": "ghost", "op": "answered"})
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(example))
    with pytest.raises(CommandError):
        call_command("validate_definition", str(bad))


@pytest.mark.django_db
def test_load_command_and_startup_loader(tmp_path, example, settings, capsys):
    example["translation_status"]["fr"] = "machine"
    (tmp_path / "a.json").write_text(json.dumps(example))
    call_command("load_definition", str(tmp_path))
    assert "created" in capsys.readouterr().out
    settings.PROLOG_DEFINITION_DIRS = [str(tmp_path)]
    call_command("load_definitions")
    assert "unchanged" in capsys.readouterr().out
    with pytest.raises(CommandError):
        call_command("load_definition", str(tmp_path), "--activate")  # fr is machine
    call_command("load_definition", str(tmp_path), "--activate", "--allow-unreviewed")
    assert "activated" in capsys.readouterr().out


def test_validate_command_fails_when_no_file_matches(tmp_path):
    # A typo'd path must not pass a CI gate silently.
    with pytest.raises(CommandError, match="no definition files"):
        call_command("validate_definition", str(tmp_path / "missing.json"))


# --- machine languages, offered deliberately and disclosed --------------------


def test_activation_still_refuses_an_unreviewed_language_by_default(db, example):
    """With the setting unset, DEF-5 behaves exactly as it did."""
    example["translation_status"]["es"] = "machine"

    with pytest.raises(loader.ActivationError, match="not reviewed"):
        loader.load_definition(example, activate=True)


def test_a_named_machine_language_may_be_activated(db, example, settings):
    """A deployment that consciously offers a machine translation, and says so."""
    example["translation_status"]["es"] = "machine"
    settings.PROLOG_MACHINE_LANGUAGES = ["es"]

    result = loader.load_definition(example, activate=True)

    assert result.version.status == "active"


def test_a_language_not_named_still_blocks(db, example, settings):
    """Naming one language is not naming them all."""
    example["translation_status"]["es"] = "machine"
    example["translation_status"]["fr"] = "machine"
    settings.PROLOG_MACHINE_LANGUAGES = ["es"]

    with pytest.raises(loader.ActivationError, match="fr"):
        loader.load_definition(example, activate=True)


def test_the_refusal_says_what_the_two_ways_past_it_are(db, example):
    example["translation_status"]["es"] = "machine"

    with pytest.raises(loader.ActivationError, match="PROLOG_MACHINE_LANGUAGES"):
        loader.load_definition(example, activate=True)


def test_reviewing_a_language_needs_no_setting(db, example, settings):
    """Flipping machine -> reviewed removes the disclosure with nothing else to change."""
    settings.PROLOG_MACHINE_LANGUAGES = []
    example["translation_status"]["es"] = "reviewed"
    example["translation_status"]["fr"] = "reviewed"

    assert loader.load_definition(example, activate=True).version.status == "active"


def test_allow_unreviewed_remains_the_preview_route(db, example, settings):
    """--allow-unreviewed is 'I am previewing'; the setting is 'respondents will
    read this'. Neither implies the other."""
    settings.PROLOG_MACHINE_LANGUAGES = []
    example["translation_status"]["es"] = "machine"

    result = loader.load_definition(example, activate=True, allow_unreviewed=True)

    assert result.version.status == "active"
