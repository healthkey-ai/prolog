"""Runner API (RUN-*, CON-3, CON-6). The response UUID is the capability token."""

from __future__ import annotations

import hashlib
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import conf
from ..engine.answers import AnswerError, option_keys_of, validate_answer
from ..engine.cascade import apply_cascade
from ..engine.completion import missing_keys, progress
from ..engine.localize import localize, pick, resolve_language
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
    version = survey.active_version
    today = timezone.now().date()
    if version is None:
        raise NotFound("survey is not active")
    if survey.effective_from and survey.effective_from > today:
        raise NotFound("survey is not yet open")
    if survey.effective_to and survey.effective_to < today:
        raise NotFound("survey has closed")
    return survey, version


def _check_access(request, definition: dict, *, invited: bool = False) -> None:
    """Account surveys need a participant the response can be linked to (RUN-3).

    Being authenticated is not enough: without a resolvable participant the
    response could be created but never read back (``_owns``), so refuse up front.
    """
    if definition["participation"]["anonymous"] or invited:
        return
    if not request.user.is_authenticated or resolve_participant(request) is None:
        raise PermissionDenied("this survey requires an account or an invitation")


def _administration(
    request, ser_data: dict, *, survey: Survey | None = None, lock: bool = False
) -> SurveyAdministration | None:
    """The administration named by an invitation token, validated for ``survey``.

    ``lock`` takes a row lock (inside a transaction) so concurrent starts of the
    same invitation serialise instead of racing the one-to-one response link.
    """
    token = ser_data.get("invitation") or request.query_params.get("invite")
    if not token:
        return None
    qs = SurveyAdministration.objects.select_related("invitation__survey")
    if lock:
        qs = qs.select_for_update()
    try:
        administration = qs.get(pk=token)
    except (SurveyAdministration.DoesNotExist, DjangoValidationError, ValueError, TypeError) as exc:
        raise PermissionDenied("invalid invitation") from exc
    if not administration.invitation.active:
        raise PermissionDenied("invitation is no longer active")
    if survey is not None and administration.invitation.survey_id != survey.id:
        raise PermissionDenied("invitation is for another survey")
    return administration


def _owns(request, response: SurveyResponse) -> None:
    """Account surveys: only the linked participant may read or write the response."""
    if response.definition["participation"]["anonymous"]:
        return
    if response.administration_id:
        return  # the administration id in the link is the credential
    participant = resolve_participant(request)
    if participant is None or participant != response.participant_id_or_none:
        raise PermissionDenied("not your response")


def _language(request, definition: dict, fallback: str | None = None) -> str:
    return resolve_language(definition, request.query_params.get("lang") or fallback)


def _etag(version, lang: str, theme_code: str) -> str:
    return f'"{version.checksum[:16]}-{lang}-{theme_code}"'


def _response_for_definition(request, slug: str) -> SurveyResponse | None:
    """``?response=<id>``: serve the version that response is bound to (RUN-2).

    A response keeps its version when a newer one is activated, so the runner
    must render and validate against the same definition the server enforces.
    """
    raw = request.query_params.get("response")
    if not raw:
        return None
    try:
        response_id = uuid.UUID(raw)
    except ValueError as exc:
        raise NotFound("unknown response") from exc
    response = get_object_or_404(
        SurveyResponse.objects.select_related("survey_version__survey"), pk=response_id
    )
    if response.survey_version.survey.slug != slug:
        raise NotFound("response belongs to another survey")
    _owns(request, response)
    return response


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

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, slug: str):
        response = _response_for_definition(request, slug)
        if response is not None:
            survey, version = response.survey_version.survey, response.survey_version
            definition = version.definition
            lang = _language(request, definition, response.language)
        else:
            survey, version = _active_version(slug)
            definition = version.definition
            invited = False
            if not definition["participation"]["anonymous"]:
                invited = _administration(request, {}, survey=survey) is not None
            _check_access(request, definition, invited=invited)
            lang = _language(request, definition)
        theme = theme_registry.resolve(survey.theme_code)
        theme_code = theme.code if theme else "default"
        etag = _etag(version, lang, theme_code)
        if request.headers.get("If-None-Match") == etag:
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
        payload = localize(definition, lang)
        payload["theme_code"] = theme_code
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
        survey, version = _active_version(data["slug"])
        administration = _administration(request, data, survey=survey, lock=True)
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
            invited = getattr(administration.invitation, "participant_id", None)
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


class ReadOnly(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "response is submitted and read-only"
    default_code = "read_only"


class ResponseMixin:
    def get_response(self, response_id, *, lock: bool = False) -> SurveyResponse:
        qs = SurveyResponse.objects.select_related("survey_version__survey")
        if lock:
            qs = qs.select_for_update(of=("self",))
        response = get_object_or_404(qs, pk=response_id)
        _owns(self.request, response)
        return response

    def writable(self, response_id) -> SurveyResponse:
        """Lock the response row for the transaction so concurrent writes and
        submit serialise (the status/answers read below stay consistent)."""
        response = self.get_response(response_id, lock=True)
        if response.is_submitted:
            raise ReadOnly()
        return response


class ResponseDetailView(ResponseMixin, APIView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, response_id):
        return Response(_response_payload(self.get_response(response_id)))

    @transaction.atomic
    def patch(self, request, response_id):
        response = self.writable(response_id)
        ser = PatchResponseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        if "language" in data:
            if data["language"] not in response.definition["languages"]:
                raise ValidationError({"language": "not offered by this survey"})
            response.language = data["language"]
        if "last_question_key" in data:
            response.last_question_key = data["last_question_key"]
        response.save(update_fields=["language", "last_question_key", "updated_at"])
        return Response(_response_payload(response))


class AnswerView(ResponseMixin, APIView):
    throttle_classes = [ResponseThrottle]

    @transaction.atomic
    def put(self, request, response_id, question_key: str):
        response = self.writable(response_id)
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
        dead = [k for k in cascade.invalidated if k not in cascade.answers]
        if dead:
            SurveyAnswer.objects.filter(response=response, question_key__in=dead).delete()
        for key in cascade.invalidated:
            if key in cascade.answers:  # a pruned matrix keeps its surviving rows
                survivor = cascade.answers[key]
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
        response = self.writable(response_id)
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
        response = self.writable(response_id)
        ser = ContactSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        question = _email_question(definition)
        if question is None or not question["config"].get("store_separately"):
            raise NotFound("this survey has no contact capture")
        answers = response.answer_map()
        if question["key"] not in visible_keys(definition, answers):
            raise ValidationError({"email": ["contact capture is not currently shown"]})
        if (answers.get(question["key"]) or {}).get("provided") is True:
            return Response(status=status.HTTP_204_NO_CONTENT)  # retry after a lost 204
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
        response = self.writable(response_id)
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
