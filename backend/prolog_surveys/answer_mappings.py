"""Governed, deterministic translation of option keys to host patient fields.

The host owns clinical persistence. In PROMOP we use its field writer rather
than updating a projection that would be lost on refresh.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import transaction
from django.utils.module_loading import import_string
from django.views.decorators.debug import sensitive_variables

from . import conf
from .engine.answers import option_keys_of, source_keys
from .options import iso3166

PATIENT_FIELDS = (
    "disease",
    "stage",
    "gender",
    "country",
    "region",
    "first_line_therapy",
    "second_line_therapy",
    "later_therapy",
    "diagnosis_date",
    "ecog_performance_status",
)


def question_options(survey):
    """Definition-backed choices across versions, including built-in sources.

    Keys, never translated labels, identify rules. A key reused in a later
    version deliberately retains its rules; administrators must review these
    when publishing a new version.
    """
    choices = {}
    for version in survey.versions.order_by("created_at", "pk"):
        definition = version.definition
        questions = {
            q["key"]: q
            for section in definition.get("sections", [])
            for q in section.get("questions", [])
        }

        def option_keys(question, questions=questions):
            options = {o["key"] for o in question.get("options", [])}
            config = question.get("config", {})
            source = config.get("options_source")
            if source in iso3166.SOURCE_KEYS:
                options |= source_keys(config, set(iso3166.SOURCE_KEYS[source]()))
            origin = questions.get(config.get("options_from"))
            if origin:
                options |= option_keys(origin)
            return options

        for key, question in questions.items():
            if question["type"] not in ("single", "dropdown", "multi", "ranking"):
                continue
            options = option_keys(question)
            text = question.get("text", key)
            label = (
                text.get(definition["default_language"], key) if isinstance(text, dict) else text
            )
            if options:
                entry = choices.setdefault(key, {"label": label, "options": set()})
                entry["options"].update(options)
    return choices


def typed_value(patient_field, value):
    if patient_field not in PATIENT_FIELDS:
        raise ValidationError({"patient_field": "This patient field cannot be mapped."})
    if not isinstance(value, str) or not value.strip():
        raise ValidationError({"mapped_value": "A non-empty value is required."})
    value = value.strip()
    try:
        if patient_field == "diagnosis_date":
            if len(value) != 10:
                raise ValueError
            return date.fromisoformat(value)
        if patient_field == "ecog_performance_status":
            if value not in ("0", "1", "2", "3", "4", "5"):
                raise ValueError
            return int(value)
    except ValueError as exc:
        raise ValidationError(
            {"mapped_value": "Use YYYY-MM-DD for dates, or an ECOG score 0–5."}
        ) from exc
    return value


def validate_rule(rule):
    options = question_options(rule.survey)
    if rule.question_key not in options:
        raise ValidationError({"question_key": "Choose an option question from this survey."})
    if rule.answer_value not in options[rule.question_key]["options"]:
        raise ValidationError({"answer_value": "Choose a raw option key from this question."})
    value = typed_value(rule.patient_field, rule.mapped_value)
    from .patients import patient_model

    model = patient_model()
    if model:
        try:
            target = model._meta.get_field(rule.patient_field)
        except FieldDoesNotExist as exc:
            raise ValidationError(
                {"patient_field": "The host patient model lacks this field."}
            ) from exc
        if not conf.get("PROLOG_PATIENT_MAPPING_WRITER"):
            if model._meta.label_lower != "omop_core.patientrecord":
                raise ValidationError(
                    {"patient_field": "Configure PROLOG_PATIENT_MAPPING_WRITER for this host."}
                )
            from omop_core.services.field_write_service import owned_writable_fields

            if rule.patient_field not in owned_writable_fields():
                raise ValidationError(
                    {
                        "patient_field": "The host cannot durably write this target. Configure a clinical mapping adapter first."
                    }
                )
        if not conf.get("PROLOG_PATIENT_MAPPING_WRITER") and rule.patient_field in (
            "country",
            "region",
        ):
            from omop_core.models import Location

            column = "state" if rule.patient_field == "region" else "country"
            try:
                Location._meta.get_field(column).clean(value, None)
            except ValidationError as exc:
                raise ValidationError({"mapped_value": exc.messages}) from exc
        try:
            target.clean(value, None)
        except ValidationError as exc:
            raise ValidationError({"mapped_value": exc.messages}) from exc


def _writer():
    path = conf.get("PROLOG_PATIENT_MAPPING_WRITER")
    return import_string(path) if path else promop_writer


@sensitive_variables()
def promop_writer(patient, changes, *, submitted_at):
    """Use PROMOP's governed writer; unsupported projections fail explicitly.

    Custom hosts must provide a callable with this signature. It must be
    transactional and idempotent, and reject values it cannot persist.
    """
    if patient._meta.label_lower != "omop_core.patientrecord":
        raise ValidationError("Configure PROLOG_PATIENT_MAPPING_WRITER for this patient model.")
    from omop_core.services.field_write_service import apply_field_writes

    try:
        result = apply_field_writes(patient.person, changes, today=submitted_at.date())
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            "The host rejected mapping values for: " + ", ".join(sorted(changes))
        ) from exc
    if result.rejected or result.profile:
        denied = sorted(set(result.rejected) | set(result.profile))
        raise ValidationError(
            "The host cannot persist these mapping targets: "
            + ", ".join(denied)
            + ". Configure an adapter for fields authored through dedicated resources."
        )


@dataclass
class MappingPlan:
    # patient pk -> (locked/model patient, changes, source timestamp per field)
    updates: dict = field(default_factory=dict)
    matched_responses: int = 0
    conflicts: int = 0
    unlinked_responses: int = 0

    @property
    def patient_count(self):
        return len(self.updates)

    @property
    def field_count(self):
        return sum(len(changes) for _, changes, _ in self.updates.values())

    def fingerprint(self, rules):
        data = [
            [
                (r.pk, r.question_key, r.answer_value, r.patient_field, r.mapped_value)
                for r in rules
            ],
            [
                (
                    str(pk),
                    changes,
                    {key: getattr(patient, key) for key in changes},
                    {key: value.isoformat() for key, value in stamp.items()},
                )
                for pk, (patient, changes, stamp) in self.updates.items()
            ],
            self.matched_responses,
            self.conflicts,
            self.unlinked_responses,
        ]
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _response_values(response, rules):
    answers = response.answer_map()
    desired = {}
    for rule in rules:
        answer = answers.get(rule.question_key, {})
        if answer.get("skipped") or rule.answer_value not in option_keys_of(answer):
            continue
        value = typed_value(rule.patient_field, rule.mapped_value)
        desired.setdefault(rule.patient_field, set()).add(value)
    # Ambiguous selections never pick a value by row order.
    return {key: next(iter(values)) for key, values in desired.items() if len(values) == 1}, sum(
        len(values) > 1 for values in desired.values()
    )


def _linked_patient_id(response):
    from .models import SurveyLinkedContact

    try:
        contact = response.linked_contact
    except SurveyLinkedContact.DoesNotExist:
        return None
    return getattr(contact, "patient_id", None)


def _patient_responses(responses, patient_id):
    return responses.filter(linked_contact__patient_id=patient_id)


def plan_mappings(survey, *, response=None, lock=False):
    from .models import SurveyAnswerMapping, SurveyResponse
    from .patients import patient_model

    rules = list(SurveyAnswerMapping.objects.filter(survey=survey).order_by("pk"))
    plan = MappingPlan()
    model = patient_model()
    if model is None or not rules:
        return plan, rules
    responses = (
        SurveyResponse.objects.filter(survey_version__survey=survey, status="submitted")
        .select_related("survey_version", "linked_contact")
        .prefetch_related("answers")
        .order_by("submitted_at", "started_at", "pk")
    )
    target_patient_id = _linked_patient_id(response) if response is not None else None
    if response is not None:
        if target_patient_id is None:
            return plan, rules
        responses = _patient_responses(responses, target_patient_id)
    candidates = {}
    for item in responses.iterator(chunk_size=200):
        values, conflicts = _response_values(item, rules)
        plan.conflicts += conflicts
        if not values:
            continue
        patient_id = _linked_patient_id(item)
        if patient_id is None:
            plan.unlinked_responses += 1
            continue
        if response is not None and patient_id != target_patient_id:
            continue
        plan.matched_responses += 1
        accumulated, timestamps = candidates.setdefault(patient_id, ({}, {}))
        accumulated.update(values)
        timestamps.update({key: item.submitted_at for key in values})
    # All clinical paths lock projections in primary-key order. Chronological
    # response order determines precedence, never database lock order.
    patients = model.objects.filter(pk__in=candidates).order_by("pk")
    if lock:
        patients = patients.select_for_update()
    for patient in patients.iterator(chunk_size=200):
        changes, timestamps = candidates[patient.pk]
        changes = {key: value for key, value in changes.items() if getattr(patient, key) != value}
        if changes:
            plan.updates[patient.pk] = (patient, changes, {key: timestamps[key] for key in changes})
    return plan, rules


@sensitive_variables()
def apply_plan(plan):
    writer = _writer()
    for patient, changes, timestamps in plan.updates.values():
        groups = {}
        for key, value in changes.items():
            groups.setdefault(timestamps[key], {})[key] = value
        for submitted_at, fields in sorted(groups.items()):
            writer(patient, fields, submitted_at=submitted_at)
            patient.refresh_from_db(fields=list(fields))
            missing = [key for key, value in fields.items() if getattr(patient, key) != value]
            if missing:
                raise ValidationError(
                    "The host did not persist mapping targets: " + ", ".join(sorted(missing))
                )


@transaction.atomic
@sensitive_variables()
def apply_response_mappings(response):
    """Public hook for forward submissions and host backfills after linkage."""
    from .models import Survey

    survey = Survey.objects.select_for_update().get(pk=response.survey_version.survey_id)
    plan, _ = plan_mappings(survey, response=response, lock=True)
    apply_plan(plan)
    return plan
