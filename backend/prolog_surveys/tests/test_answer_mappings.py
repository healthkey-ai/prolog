"""Mapping governance, deterministic plans, host writes and admin permissions."""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, models
from django.urls import reverse
from django.utils import timezone

from prolog_surveys import answer_mappings as mapping
from prolog_surveys.definitions.loader import load_definition
from prolog_surveys.models import SurveyAnswer, SurveyAnswerMapping
from prolog_surveys.tests.conftest import make_response

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def admin_static_files(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def survey(example):
    return load_definition(example).version.survey


def rule(survey, **overrides):
    values = dict(
        question_key="country",
        answer_value="US",
        patient_field="country",
        mapped_value="United States",
    )
    values.update(overrides)
    return SurveyAnswerMapping.objects.create(survey=survey, **values)


@pytest.mark.parametrize(
    "overrides",
    [
        {"question_key": "missing"},
        {"question_key": "birth_year"},
        {"answer_value": "not-an-option"},
        {"patient_field": "email"},
        {"patient_field": "diagnosis_date", "mapped_value": "2025-99-01"},
        {"patient_field": "ecog_performance_status", "mapped_value": "6"},
        {"mapped_value": " "},
    ],
)
def test_rule_rejects_invalid_targets_and_keys(survey, overrides):
    item = rule(survey, **overrides)
    with pytest.raises(ValidationError):
        item.clean()


def test_country_sources_and_typed_values(survey):
    rule(survey).clean()
    assert "US" in mapping.question_options(survey)["country"]["options"]
    assert mapping.typed_value("diagnosis_date", "2025-01-02") == date(2025, 1, 2)
    assert mapping.typed_value("ecog_performance_status", "0") == 0


def submitted(survey, *, answers=None, when=None, status="submitted"):
    response = make_response(
        survey.versions.first(), language="en", status=status, submitted_at=when or timezone.now()
    )
    for key, value in (answers or {"country": {"option": "US"}}).items():
        SurveyAnswer.objects.create(response=response, question_key=key, value=value)
    return response


class MappingPatient(models.Model):
    country = models.CharField(max_length=255, default="")
    stage = models.TextField(default="")
    ecog_performance_status = models.IntegerField(null=True)
    diagnosis_date = models.DateField(null=True)

    class Meta:
        app_label = "prolog_mapping_test"
        managed = False
        db_table = "test_mapping_patient"

    def __str__(self):
        return str(self.pk)


@pytest.fixture
def patient_model(monkeypatch):
    """A rich host-owned patient model, without fake auth.User clinical fields."""
    with connection.schema_editor() as editor:
        editor.create_model(MappingPatient)
    from prolog_surveys import mapping_admin, patients

    monkeypatch.setattr(patients, "patient_model", lambda: MappingPatient)
    monkeypatch.setattr(mapping_admin, "patient_model", lambda: MappingPatient)
    monkeypatch.setattr(mapping, "_patient_responses", lambda responses, patient_id: responses)
    yield MappingPatient
    with connection.schema_editor() as editor:
        editor.delete_model(MappingPatient)


def direct_writer(patient, changes, *, submitted_at):
    for key, value in changes.items():
        setattr(patient, key, value)
    patient.save(update_fields=list(changes))


@pytest.mark.django_db(transaction=True)
def test_plan_latest_submission_wins_and_reapply_is_noop(
    survey, patient_model, monkeypatch, settings
):
    patient = patient_model.objects.create(country="Old")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    settings.PROLOG_PATIENT_MAPPING_WRITER = (
        "prolog_surveys.tests.test_answer_mappings.direct_writer"
    )
    rule(survey)
    rule(survey, answer_value="GB", mapped_value="United Kingdom")
    submitted(survey, when=timezone.now() - timedelta(days=1))
    latest = submitted(survey, answers={"country": {"option": "GB"}})
    submitted(survey, status="in_progress")
    plan, _ = mapping.plan_mappings(survey)
    assert plan.matched_responses == 2
    assert plan.patient_count == plan.field_count == 1
    mapping.apply_response_mappings(latest)
    patient.refresh_from_db()
    assert patient.country == "United Kingdom"
    assert mapping.plan_mappings(survey)[0].patient_count == 0


@pytest.mark.django_db(transaction=True)
def test_unlinked_skipped_and_conflicting_answers_do_not_write(survey, patient_model, monkeypatch):
    rule(
        survey,
        question_key="symptoms",
        answer_value="fatigue",
        patient_field="stage",
        mapped_value="I",
    )
    rule(
        survey,
        question_key="symptoms",
        answer_value="pain",
        patient_field="stage",
        mapped_value="II",
    )
    submitted(survey, answers={"symptoms": {"options": ["fatigue", "pain"]}})
    submitted(survey)
    submitted(survey, answers={"country": {"skipped": True}})
    rule(survey)
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: None)
    plan, _ = mapping.plan_mappings(survey)
    assert plan.conflicts == 1
    assert plan.unlinked_responses == 1
    assert plan.patient_count == 0


@pytest.mark.django_db(transaction=True)
def test_writer_failure_rolls_back_entire_forward_application(
    survey, patient_model, monkeypatch, settings
):
    patient = patient_model.objects.create(country="Old")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    rule(survey)
    response = submitted(survey)

    def failing_writer(patient, changes, *, submitted_at):
        direct_writer(patient, changes, submitted_at=submitted_at)
        raise ValidationError("Unsupported host write")

    monkeypatch.setattr(mapping, "_writer", lambda: failing_writer)
    with pytest.raises(ValidationError):
        mapping.apply_response_mappings(response)
    patient.refresh_from_db()
    assert patient.country == "Old"


def test_default_writer_requires_explicit_custom_host_adapter():
    patient = SimpleNamespace(_meta=SimpleNamespace(label_lower="auth.user"))
    with pytest.raises(ValidationError, match="PROLOG_PATIENT_MAPPING_WRITER"):
        mapping.promop_writer(patient, {"country": "X"}, submitted_at=timezone.now())


def test_admin_editor_validates_rules_and_is_permission_gated(survey, client):
    user = get_user_model().objects.create_user(username="mapping-staff", is_staff=True)
    client.force_login(user)
    url = reverse("admin:prolog_surveys_survey_mappings", args=[survey.pk]) + "?question=country"
    assert client.get(url).status_code == 403
    user.is_superuser = True
    user.save()
    assert client.get(url).status_code == 200
    data = {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "0",
        "form-0-answer_value": "US",
        "form-0-patient_field": "country",
        "form-0-mapped_value": "United States",
    }
    assert client.post(url, data).status_code == 302
    assert survey.answer_mappings.get().mapped_value == "United States"
    data["form-0-answer_value"] = "bogus"
    assert client.post(url, data).status_code == 200
    assert survey.answer_mappings.get().answer_value == "US"


@pytest.mark.django_db(transaction=True)
def test_admin_requires_preview_then_applies_and_rejects_stale_preview(
    survey, patient_model, monkeypatch, settings, admin_client
):
    patient = patient_model.objects.create(country="Old")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    settings.PROLOG_PATIENT_MAPPING_WRITER = (
        "prolog_surveys.tests.test_answer_mappings.direct_writer"
    )
    item = rule(survey)
    submitted(survey)
    url = reverse("admin:prolog_surveys_survey_mapping_preview", args=[survey.pk])
    preview = admin_client.get(url)
    assert preview.context_data["plan"].patient_count == 1
    token = preview.context_data["preview"]
    item.mapped_value = "Changed"
    item.save()
    stale = admin_client.post(url, {"preview": token})
    assert "data changed" in stale.context_data["error"]
    patient.refresh_from_db()
    assert patient.country == "Old"
    fresh = stale.context_data["preview"]
    assert admin_client.post(url, {"preview": fresh}).status_code == 302
    patient.refresh_from_db()
    assert patient.country == "Changed"


def test_submit_hook_applies_after_patient_linkage(survey, api_client, monkeypatch):
    """The runner, not only a backfill caller, invokes approved mappings."""
    response = make_response(survey.versions.first(), language="en")
    calls = []
    from prolog_surveys.api import views

    monkeypatch.setattr(views, "_state", lambda *args, **kwargs: {"missing": []})
    monkeypatch.setattr(views, "_response_payload", lambda *args, **kwargs: {})
    monkeypatch.setattr(views, "link_submitted_response", lambda response: calls.append("link"))
    monkeypatch.setattr(views, "apply_response_mappings", lambda response: calls.append("map"))
    result = api_client.post(reverse("run-submit", args=[response.pk]))
    assert result.status_code == 200
    assert calls == ["link", "map"]


@pytest.mark.django_db(transaction=True)
def test_replaying_older_submission_cannot_replace_newer_patient_value(
    survey, patient_model, monkeypatch, settings
):
    patient = patient_model.objects.create(country="United Kingdom")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    settings.PROLOG_PATIENT_MAPPING_WRITER = (
        "prolog_surveys.tests.test_answer_mappings.direct_writer"
    )
    rule(survey)
    rule(survey, answer_value="GB", mapped_value="United Kingdom")
    older = submitted(survey, when=timezone.now() - timedelta(days=1))
    submitted(survey, answers={"country": {"option": "GB"}})
    assert mapping.apply_response_mappings(older).patient_count == 0
    patient.refresh_from_db()
    assert patient.country == "United Kingdom"


def test_editor_empty_extra_rows_are_valid(survey):
    from django.forms import formset_factory

    from prolog_surveys.mapping_admin import RuleForm

    formset = formset_factory(RuleForm, extra=1)(
        {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-0-answer_value": "US",
            "form-0-patient_field": "country",
            "form-0-mapped_value": "United States",
            "form-1-answer_value": "",
            "form-1-patient_field": "",
            "form-1-mapped_value": "",
        },
        form_kwargs={"survey": survey, "question_key": "country"},
    )
    assert formset.is_valid(), formset.errors


def test_staff_cannot_publish_forward_rules_without_patient_write_permission(
    survey, client, monkeypatch
):
    from django.contrib.auth.models import Permission

    from prolog_surveys import mapping_admin

    monkeypatch.setattr(mapping_admin, "patient_model", get_user_model)
    user = get_user_model().objects.create_user(username="mapping-curator", is_staff=True)
    user.user_permissions.add(
        *Permission.objects.filter(
            codename__in=["view_surveyanswermapping", "change_surveyanswermapping"]
        )
    )
    client.force_login(user)
    url = reverse("admin:prolog_surveys_survey_mappings", args=[survey.pk]) + "?question=country"
    assert client.get(url).status_code == 200
    assert client.post(url, {}).status_code == 403
    assert not survey.answer_mappings.exists()


@pytest.mark.django_db(transaction=True)
def test_host_writer_receives_original_date_for_each_winning_field(
    survey, patient_model, monkeypatch
):
    patient = patient_model.objects.create(country="Old", stage="Old")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    calls = []

    def recording_writer(patient, changes, *, submitted_at):
        calls.append((changes, submitted_at))
        direct_writer(patient, changes, submitted_at=submitted_at)

    monkeypatch.setattr(mapping, "_writer", lambda: recording_writer)
    rule(
        survey,
        question_key="age_band",
        answer_value="under_30",
        patient_field="stage",
        mapped_value="I",
    )
    rule(survey)
    earlier = submitted(
        survey,
        when=timezone.now() - timedelta(days=2),
        answers={"age_band": {"option": "under_30"}},
    )
    later = submitted(survey)
    mapping.apply_response_mappings(later)
    assert calls == [
        ({"stage": "I"}, earlier.submitted_at),
        ({"country": "United States"}, later.submitted_at),
    ]


@pytest.mark.parametrize("failure", ["rejected", "profile", "value_error"])
def test_promop_writer_rejects_partial_or_invalid_host_results(monkeypatch, failure):
    import sys
    from types import ModuleType

    module = ModuleType("omop_core.services.field_write_service")

    def write(*args, **kwargs):
        if failure == "value_error":
            raise ValueError("clinical source constraint")
        return SimpleNamespace(
            rejected={"stage": "unsupported"} if failure == "rejected" else {},
            profile={"stage": "not persisted"} if failure == "profile" else {},
        )

    module.apply_field_writes = write
    monkeypatch.setitem(sys.modules, module.__name__, module)
    patient = SimpleNamespace(
        _meta=SimpleNamespace(label_lower="omop_core.patientrecord"), person=object()
    )
    with pytest.raises(ValidationError):
        mapping.promop_writer(patient, {"stage": "I"}, submitted_at=timezone.now())


@pytest.mark.django_db(transaction=True)
def test_silent_host_writer_is_detected_and_rolled_back(survey, patient_model, monkeypatch):
    patient = patient_model.objects.create(country="Old")
    monkeypatch.setattr(mapping, "_linked_patient_id", lambda response: patient.pk)
    monkeypatch.setattr(mapping, "_writer", lambda: lambda *args, **kwargs: None)
    rule(survey)
    response = submitted(survey)
    with pytest.raises(ValidationError, match="did not persist"):
        mapping.apply_response_mappings(response)
    patient.refresh_from_db()
    assert patient.country == "Old"


def test_failed_forward_mapping_keeps_response_retryable_without_leaking_data(
    survey, api_client, monkeypatch, caplog
):
    response = make_response(survey.versions.first(), language="en")
    from prolog_surveys.api import views

    monkeypatch.setattr(views, "_state", lambda *args, **kwargs: {"missing": []})
    monkeypatch.setattr(views, "link_submitted_response", lambda response: None)

    def fail(response):
        raise ValueError("private-patient@example.org")

    monkeypatch.setattr(views, "apply_response_mappings", fail)
    result = api_client.post(reverse("run-submit", args=[response.pk]))
    assert result.status_code == 503
    response.refresh_from_db()
    assert response.status == "in_progress"
    assert response.submitted_at is None
    assert "private-patient" not in result.content.decode()
    assert "private-patient" not in caplog.text
