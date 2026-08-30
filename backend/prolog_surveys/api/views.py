"""Runner API (RUN-*, CON-3, CON-6). The response UUID is the capability token."""

from __future__ import annotations

import hashlib

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import conf
from ..engine.answers import AnswerError, option_keys_of, validate_answer
from ..engine.cascade import apply_cascade
from ..engine.completion import missing_keys, progress
from ..engine.localize import localize, pick
from ..engine.visibility import question_by_key, visible_keys
from ..identity import (
    IdentityRequest,
    IdentityServiceError,
    get_identity_service,
    idempotency_key,
    resolve_participant,
)
from ..invitations import version_for
from ..models import (
    LifecycleStatus,
    ResponseStatus,
    Survey,
    SurveyAdministration,
    SurveyAnswer,
    SurveyConsent,
    SurveyContact,
    SurveyResponse,
)
from ..options import iso3166
from ..themes import registry as theme_registry
from .serializers import (
    AnswerSerializer,
    ContactSerializer,
    CreateResponseSerializer,
    IdentitySerializer,
    PatchResponseSerializer,
    ResponseSerializer,
)
from .throttles import ClientKeyThrottle, CreateThrottle, ResponseThrottle


def _active_version(slug: str):
    survey = get_object_or_404(Survey, slug=slug)
    version = survey.versions.filter(status=LifecycleStatus.ACTIVE).first()
    today = timezone.now().date()
    if version is None:
        raise NotFound("survey is not active")
    if survey.effective_from and survey.effective_from > today:
        raise NotFound("survey is not yet open")
    if survey.effective_to and survey.effective_to < today:
        raise NotFound("survey has closed")
    return survey, version


def _check_access(request, definition: dict, *, invited: bool = False) -> None:
    if definition["participation"]["anonymous"] or invited:
        return
    if not request.user.is_authenticated:
        raise PermissionDenied("this survey requires an account or an invitation")


def _administration(request, ser_data: dict) -> SurveyAdministration | None:
    token = ser_data.get("invitation") or request.query_params.get("invite")
    if not token:
        return None
    try:
        return SurveyAdministration.objects.select_related("invitation__survey").get(pk=token)
    except (SurveyAdministration.DoesNotExist, DjangoValidationError, ValueError, TypeError) as exc:
        raise PermissionDenied("invalid invitation") from exc


def _owns(request, response: SurveyResponse) -> None:
    """Account surveys: only the linked participant may read or write the response."""
    if response.definition["participation"]["anonymous"]:
        return
    if response.administration_id:
        return  # the administration id in the link is the credential
    participant = resolve_participant(request)
    if participant is None or participant != response.participant_id_or_none:
        raise PermissionDenied("not your response")


def _language(request, definition: dict) -> str:
    lang = request.query_params.get("lang") or definition["default_language"]
    return lang if lang in definition["languages"] else definition["default_language"]


def _etag(version, lang: str) -> str:
    return f'"{version.checksum[:16]}-{lang}"'


def _response_payload(response: SurveyResponse) -> dict:
    definition = response.definition
    answers = response.answer_map()
    data = ResponseSerializer(response).data
    data["answers"] = answers
    data["visible"] = visible_keys(definition, answers)
    data["missing"] = missing_keys(definition, answers)
    data["progress"] = progress(definition, answers)
    return data


class SurveyDefinitionView(APIView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, slug: str):
        survey, version = _active_version(slug)
        definition = version.definition
        _check_access(request, definition, invited=_administration(request, {}) is not None)
        lang = _language(request, definition)
        etag = _etag(version, lang)
        if request.headers.get("If-None-Match") == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        payload = localize(definition, lang)
        theme = theme_registry.resolve(survey.theme_code)
        payload["theme_code"] = theme.code if theme else "default"
        payload["translation_status"] = definition.get("translation_status", {})
        return Response(payload, headers={"ETag": etag, "Cache-Control": "private, max-age=60"})


class OptionsSourceView(APIView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, source: str):
        provider = iso3166.SOURCES.get(source)
        if provider is None:
            raise NotFound("unknown option source")
        lang = request.query_params.get("lang", "en")
        return Response(
            {"source": source, "language": lang, "options": provider(lang)},
            headers={"Cache-Control": "public, max-age=86400"},
        )


class ResponseCreateView(APIView):
    throttle_classes = [CreateThrottle]

    @transaction.atomic
    def post(self, request):
        ser = CreateResponseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        administration = _administration(request, data)
        if administration is not None and administration.invitation.survey.slug != data["slug"]:
            raise PermissionDenied("invitation is for another survey")
        survey, version = _active_version(data["slug"])
        if administration is not None:
            version = version_for(administration) or version
        definition = version.definition
        _check_access(request, definition, invited=administration is not None)
        lang = data["language"]
        if lang not in definition["languages"]:
            raise ValidationError({"language": "not offered by this survey"})

        # Account resume (RUN-3): return the participant's in-progress response.
        participant = (
            None if definition["participation"]["anonymous"] else resolve_participant(request)
        )
        if administration is not None and getattr(administration, "response", None) is not None:
            return Response(_response_payload(administration.response), status=status.HTTP_200_OK)
        if participant is not None and definition["participation"].get("resume") == "account":
            existing = (
                SurveyResponse.objects.filter(
                    survey_version=version,
                    status=ResponseStatus.IN_PROGRESS,
                    participant_id=participant,
                )
                .order_by("-started_at")
                .first()
            )
            if existing is not None:
                return Response(_response_payload(existing), status=status.HTTP_200_OK)

        consent_cfg = definition.get("consent")
        consent = data.get("consent")
        if consent_cfg and consent_cfg.get("required", True):
            if (
                not consent
                or consent.get("version") != consent_cfg["version"]
                or not consent.get("agreed")
            ):
                raise ValidationError(
                    {"consent": "agreement to the current consent notice is required"}
                )
        ua = request.META.get("HTTP_USER_AGENT", "")
        ua_hash = (
            hashlib.sha256(f"{conf.get('PROLOG_CLIENT_KEY_SALT')}|{ua}".encode()).hexdigest()
            if ua
            else ""
        )
        fields = {"survey_version": version, "language": lang, "user_agent_hash": ua_hash}
        if administration is not None:
            fields["administration"] = administration
            invited = (
                administration.invitation.participant_id_or_none
                if hasattr(administration.invitation, "participant_id_or_none")
                else getattr(administration.invitation, "participant_id", None)
            )
            if invited is not None:
                fields["participant_id"] = invited
        elif participant is not None:
            fields["participant_id"] = participant
        response = SurveyResponse.objects.create(**fields)
        if consent_cfg and consent:
            text = pick(consent_cfg["text"], lang, definition["default_language"])
            SurveyConsent.objects.create(
                response=response,
                consent_version=consent_cfg["version"],
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                language=lang,
            )
        return Response(_response_payload(response), status=status.HTTP_201_CREATED)


class ResponseMixin:
    def get_response(self, response_id) -> SurveyResponse:
        response = get_object_or_404(
            SurveyResponse.objects.select_related("survey_version__survey"), pk=response_id
        )
        _owns(self.request, response)
        return response

    def writable(self, response_id) -> SurveyResponse:
        response = self.get_response(response_id)
        if response.is_submitted:
            raise ReadOnly()
        return response


class ReadOnly(Exception):
    pass


def _read_only():
    return Response(
        {"detail": "response is submitted and read-only"}, status=status.HTTP_409_CONFLICT
    )


class ResponseDetailView(ResponseMixin, APIView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, response_id):
        return Response(_response_payload(self.get_response(response_id)))

    def patch(self, request, response_id):
        try:
            response = self.writable(response_id)
        except ReadOnly:
            return _read_only()
        ser = PatchResponseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "language" in data:
            if data["language"] not in response.definition["languages"]:
                raise ValidationError({"language": "not offered by this survey"})
            response.language = data["language"]
        if "last_question_key" in data:
            response.last_question_key = data["last_question_key"]
        response.save()
        return Response(_response_payload(response))


class AnswerView(ResponseMixin, APIView):
    throttle_classes = [ResponseThrottle]

    @transaction.atomic
    def put(self, request, response_id, question_key: str):
        try:
            response = self.writable(response_id)
        except ReadOnly:
            return _read_only()
        ser = AnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        questions = question_by_key(definition)
        question = questions.get(question_key)
        if question is None:
            raise NotFound("unknown question")
        answers = response.answer_map()
        if question_key not in visible_keys(definition, answers):
            raise ValidationError({"value": ["this question is not currently shown"]})
        source_options = None
        if question["type"] == "dropdown" and question["config"].get("options_source"):
            source_options = set(iso3166.SOURCE_KEYS[question["config"]["options_source"]]())
        try:
            value = validate_answer(
                question,
                ser.validated_data["value"],
                answers,
                presentation=definition["presentation"],
                source_options=source_options,
            )
        except AnswerError as exc:
            raise ValidationError({"value": exc.errors}) from exc
        answers[question_key] = value
        cascade = apply_cascade(definition, answers)
        answer, _ = SurveyAnswer.objects.update_or_create(
            response=response,
            question_key=question_key,
            defaults={"value": value, "option_keys": option_keys_of(value)},
        )
        for key in cascade.invalidated:
            survivor = cascade.answers.get(key)
            if survivor is None:
                SurveyAnswer.objects.filter(response=response, question_key=key).delete()
            else:
                SurveyAnswer.objects.filter(response=response, question_key=key).update(
                    value=survivor, option_keys=option_keys_of(survivor)
                )
        response.last_question_key = question_key
        response.save(update_fields=["last_question_key", "updated_at"])
        return Response(
            {
                "answer": {"key": question_key, "value": value},
                "invalidated": cascade.invalidated,
                "visible": cascade.visible,
                "missing": missing_keys(definition, cascade.answers),
                "progress": progress(definition, cascade.answers),
            }
        )


class SubmitView(ResponseMixin, APIView):
    throttle_classes = [ResponseThrottle]

    @transaction.atomic
    def post(self, request, response_id):
        try:
            response = self.writable(response_id)
        except ReadOnly:
            return _read_only()
        missing = missing_keys(response.definition, response.answer_map())
        if missing:
            return Response({"missing": missing}, status=status.HTTP_400_BAD_REQUEST)
        response.status = ResponseStatus.SUBMITTED
        response.submitted_at = timezone.now()
        response.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(_response_payload(response))


def _email_question(definition: dict) -> dict | None:
    for q in question_by_key(definition).values():
        if q["type"] == "email":
            return q
    return None


class ContactView(ResponseMixin, APIView):
    """Contact capture (CON-3): the address is stored with no link to the response."""

    throttle_classes = [ResponseThrottle]

    @transaction.atomic
    def post(self, request, response_id):
        try:
            response = self.writable(response_id)
        except ReadOnly:
            return _read_only()
        ser = ContactSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        question = _email_question(definition)
        if question is None or not question["config"].get("store_separately"):
            raise NotFound("this survey has no contact capture")
        answers = response.answer_map()
        if question["key"] not in visible_keys(definition, answers):
            raise ValidationError({"email": ["contact capture is not currently shown"]})
        notice = pick(
            question.get("help", {}) or question["text"],
            response.language,
            definition["default_language"],
        )
        SurveyContact.objects.create(
            survey_version=response.survey_version,
            email=ser.validated_data["email"],
            language=response.language,
            consent_text=notice,
        )
        SurveyAnswer.objects.update_or_create(
            response=response,
            question_key=question["key"],
            defaults={"value": {"provided": True}, "option_keys": []},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class IdentityView(ResponseMixin, APIView):
    """Identity capture (CON-4): the email goes to the host platform's identity service only."""

    throttle_classes = [ResponseThrottle]

    @transaction.atomic
    def post(self, request, response_id):
        try:
            response = self.writable(response_id)
        except ReadOnly:
            return _read_only()
        if not conf.is_integrated():
            raise NotFound("identity capture is only available in the integrated profile")
        ser = IdentitySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        question = _email_question(definition)
        if question is None or not question["config"].get("link_identity"):
            raise NotFound("this survey has no identity capture")
        if question["key"] not in visible_keys(definition, response.answer_map()):
            raise ValidationError({"email": ["identity capture is not currently shown"]})
        service = get_identity_service()
        if service is None:
            raise NotFound("no identity service is configured")
        if response.participant_id_or_none is None:
            try:
                result = service.create_or_link(
                    IdentityRequest(
                        email=ser.validated_data["email"],
                        idempotency_key=idempotency_key(response.id),
                        survey_slug=response.survey_version.survey.slug,
                        language=response.language,
                    )
                )
            except IdentityServiceError as exc:
                return (
                    Response(
                        {
                            "detail": "identity service unavailable; you can still submit anonymously"
                        },
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                    if str(exc)
                    else Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
                )
            response.participant_id = result.participant_pk
            response.identity_linked_at = timezone.now()
            response.save(update_fields=["participant", "identity_linked_at", "updated_at"])
        SurveyAnswer.objects.update_or_create(
            response=response,
            question_key=question["key"],
            defaults={"value": {"provided": True}, "option_keys": []},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
