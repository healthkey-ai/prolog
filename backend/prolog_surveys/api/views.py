"""Runner API (RUN-*, CON-3, CON-6). The response UUID is the capability token."""

from __future__ import annotations

import hashlib

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
from ..models import (
    LifecycleStatus,
    ResponseStatus,
    Survey,
    SurveyAnswer,
    SurveyConsent,
    SurveyContact,
    SurveyResponse,
)
from ..options import iso3166
from .serializers import (
    AnswerSerializer,
    ContactSerializer,
    CreateResponseSerializer,
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


def _check_access(request, definition: dict) -> None:
    if definition["participation"]["anonymous"]:
        return
    if not request.user.is_authenticated:
        raise PermissionDenied("this survey requires an account")


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
        _check_access(request, definition)
        lang = _language(request, definition)
        etag = _etag(version, lang)
        if request.headers.get("If-None-Match") == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        payload = localize(definition, lang)
        payload["theme_code"] = survey.theme_code or "default"
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
        survey, version = _active_version(ser.validated_data["slug"])
        definition = version.definition
        _check_access(request, definition)
        lang = ser.validated_data["language"]
        if lang not in definition["languages"]:
            raise ValidationError({"language": "not offered by this survey"})
        consent_cfg = definition.get("consent")
        consent = ser.validated_data.get("consent")
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
        response = SurveyResponse.objects.create(
            survey_version=version, language=lang, user_agent_hash=ua_hash
        )
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
        return get_object_or_404(
            SurveyResponse.objects.select_related("survey_version__survey"), pk=response_id
        )

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
