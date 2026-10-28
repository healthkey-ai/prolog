"""Survey-scoped mapping editor and explicit preview/apply workflow."""

import logging

from django import forms
from django.contrib import messages
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import formset_factory
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from .answer_mappings import PATIENT_FIELDS, apply_plan, plan_mappings, question_options
from .models import Survey, SurveyAnswerMapping
from .patients import patient_model

log = logging.getLogger(__name__)


class RuleForm(forms.Form):
    answer_value = forms.ChoiceField(label="Answer key")
    patient_field = forms.ChoiceField(
        choices=[("", "Choose a field"), *[(key, key) for key in PATIENT_FIELDS]]
    )
    mapped_value = forms.CharField(widget=forms.TextInput(attrs={"size": 35}))

    def __init__(self, *args, survey, question_key, **kwargs):
        super().__init__(*args, **kwargs)
        self.survey = survey
        self.question_key = question_key
        for name, label in (
            ("answer_value", "Answer key"),
            ("patient_field", "Patient field"),
            ("mapped_value", "Mapped value"),
        ):
            self.fields[name].widget.attrs["aria-label"] = label
        options = question_options(survey).get(question_key, {}).get("options", ())
        self.fields["answer_value"].choices = [
            ("", "Choose an answer"),
            *[(key, key) for key in sorted(options)],
        ]

    def clean(self):
        data = super().clean()
        if all(key in data for key in ("answer_value", "patient_field", "mapped_value")):
            rule = SurveyAnswerMapping(
                survey=self.survey,
                question_key=self.question_key,
                **{key: data[key] for key in ("answer_value", "patient_field", "mapped_value")},
            )
            try:
                rule.clean()
            except ValidationError as exc:
                for key, errors in exc.message_dict.items():
                    self.add_error(key if key in self.fields else None, errors)
        return data


def _allowed(request, *, edit=False, apply=False):
    action = "change" if edit else "view"
    if not request.user.has_perm(f"prolog_surveys.{action}_surveyanswermapping"):
        raise PermissionDenied
    if apply or edit:
        model = patient_model()
        if model is None:
            if apply:
                raise PermissionDenied
        elif not request.user.has_perm(f"{model._meta.app_label}.change_{model._meta.model_name}"):
            raise PermissionDenied


def editor(admin, request, survey_id):
    _allowed(request, edit=request.method == "POST")
    survey = get_object_or_404(Survey, pk=survey_id)
    questions = question_options(survey)
    key = request.GET.get("question", "")
    if key and key not in questions:
        from django.http import Http404

        raise Http404
    rules = list(survey.answer_mappings.filter(question_key=key)) if key else []
    forms_class = formset_factory(
        RuleForm, extra=3, can_delete=True, max_num=1000, validate_max=True
    )
    formset = (
        forms_class(
            request.POST if request.method == "POST" else None,
            initial=[
                {
                    "answer_value": rule.answer_value,
                    "patient_field": rule.patient_field,
                    "mapped_value": rule.mapped_value,
                }
                for rule in rules
            ],
            form_kwargs={"survey": survey, "question_key": key},
        )
        if key
        else None
    )
    if request.method == "POST" and formset is not None and formset.is_valid():
        rows = [
            form.cleaned_data
            for form in formset
            if form.cleaned_data and not form.cleaned_data.get("DELETE")
        ]
        identities = [(row["answer_value"], row["patient_field"]) for row in rows]
        if len(set(identities)) != len(identities):
            admin.message_user(
                request, "Each answer key and patient field pair must be unique.", messages.ERROR
            )
        else:
            with transaction.atomic():
                Survey.objects.select_for_update().get(pk=survey.pk)
                survey.answer_mappings.filter(question_key=key).delete()
                for row in rows:
                    row.pop("DELETE", None)
                    SurveyAnswerMapping.objects.create(survey=survey, question_key=key, **row)
                admin.log_change(request, survey, f"Updated patient answer mappings for {key}.")
            admin.message_user(
                request,
                "Mappings saved. Future linked submissions use these rules. Preview before applying to existing respondents.",
                messages.SUCCESS,
            )
            return redirect(request.get_full_path())
    return TemplateResponse(
        request,
        "admin/prolog_surveys/survey/mappings.html",
        {
            **admin.admin_site.each_context(request),
            "opts": admin.model._meta,
            "title": f"Patient answer mappings: {survey.slug}",
            "survey": survey,
            "questions": [(q, entry["label"]) for q, entry in questions.items()],
            "question_key": key,
            "formset": formset,
            "rules": survey.answer_mappings.all(),
            "can_edit": request.user.has_perm("prolog_surveys.change_surveyanswermapping"),
        },
    )


def preview(admin, request, survey_id):
    _allowed(request, edit=request.method == "POST", apply=request.method == "POST")
    survey = get_object_or_404(Survey, pk=survey_id)
    error = ""
    with transaction.atomic():
        if request.method == "POST":
            survey = Survey.objects.select_for_update().get(pk=survey.pk)
        plan, rules = plan_mappings(survey, lock=request.method == "POST")
        digest = plan.fingerprint(rules)
        if request.method == "POST":
            try:
                expected = signing.loads(
                    request.POST.get("preview", ""), salt="patient-mapping-preview", max_age=1800
                )
            except signing.BadSignature:
                expected = None
            if expected != [str(survey.pk), digest]:
                error = "The preview expired or its data changed. Review this fresh preview before applying."
            else:
                try:
                    # A rejected writer must roll back the complete batch.
                    with transaction.atomic():
                        apply_plan(plan)
                except ValidationError as exc:
                    error = " ".join(exc.messages)
                except Exception as exc:
                    log.error("patient mapping writer failed with %s", type(exc).__name__)
                    error = "The host mapping writer failed. No patient updates were saved."
                else:
                    admin.log_change(
                        request,
                        survey,
                        f"Applied patient mappings to {plan.patient_count} patient(s), {plan.field_count} field(s).",
                    )
                    admin.message_user(
                        request, f"Updated {plan.patient_count} patient(s).", messages.SUCCESS
                    )
                    return redirect(
                        reverse("admin:prolog_surveys_survey_mappings", args=[survey.pk])
                    )
    return TemplateResponse(
        request,
        "admin/prolog_surveys/survey/mapping_preview.html",
        {
            **admin.admin_site.each_context(request),
            "opts": admin.model._meta,
            "title": f"Preview patient mappings: {survey.slug}",
            "survey": survey,
            "plan": plan,
            "rules": rules,
            "error": error,
            "preview": signing.dumps([str(survey.pk), digest], salt="patient-mapping-preview"),
            "patient_model": patient_model(),
        },
    )
