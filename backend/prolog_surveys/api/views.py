"""Runner API (RUN-*, CON-3, CON-6). The response UUID is the capability token."""

from __future__ import annotations

import hashlib
import logging
import re
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.cache import get_conditional_response
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .. import conf
from ..engine.answers import AnswerError, issue, option_keys_of, validate_answer
from ..engine.cascade import apply_cascade, retained_when_hidden
from ..engine.completion import missing_keys, progress
from ..engine.localize import pick, resolve_language
from ..engine.visibility import VisibleQuestion, question_by_key, visible_questions
from ..identity import (
    IdentityRequest,
    IdentityServiceError,
    get_identity_service,
    idempotency_key,
    mint_participant,
    resolve_participant,
)
from ..invitations import takes_invitations, version_for
from ..models import (
    LifecycleStatus,
    MintedParticipant,
    ParticipantMergeCandidate,
    ResponseStatus,
    Survey,
    SurveyAdministration,
    SurveyAnswer,
    SurveyConsent,
    SurveyContact,
    SurveyResponse,
    SurveyVersion,
)
from ..options import iso3166
from ..themes import registry as theme_registry
from .serializers import (
    AnswerSerializer,
    ContactSerializer,
    CreateResponseSerializer,
    PatchResponseSerializer,
    ResponseSerializer,
)
from .throttles import (
    CaptureThrottle,
    ClientKeyThrottle,
    CreateThrottle,
    ResponseThrottle,
    WriteThrottle,
)

log = logging.getLogger(__name__)


def _active_version(slug: str):
    """The survey and its active version, or 404 (unknown/inactive) / 410 (outside
    the effective window — the same signal ``writable`` gives, so the runner can
    say "closed" rather than "not found"). The definition column is deferred;
    read it through ``cached_definition``."""
    survey = get_object_or_404(Survey, slug=slug)
    version = survey.versions.filter(status=LifecycleStatus.ACTIVE).defer("definition").first()
    if version is None:
        raise NotFound("survey is not active")
    error = survey.closed_reason()
    if error:
        raise SurveyClosed(error)
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
        # Only the administration row: without ``of`` PostgreSQL also locks the
        # joined invitation and survey rows for the whole start transaction.
        qs = qs.select_for_update(of=("self",))
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
    if response.administration_id and response.administration.invitation.active:
        # The administration id in the link is the credential, for as long as
        # the invitation stands.
        return
    participant = resolve_participant(request)
    if participant is not None and participant == response.participant_id_or_none:
        return
    if response.administration_id:
        # Deactivating an invitation revokes every link it sent, not the invited
        # participant's own response: signed in, they keep (and resume) it.
        raise PermissionDenied("invitation is no longer active")
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
    response = get_object_or_404(_responses(), pk=response_id)
    if response.survey_version.survey.slug != slug:
        raise NotFound("response belongs to another survey")
    _owns(request, response)
    return response


def _responses():
    """Response queryset for the runner: the definition JSON is deferred and read
    through the per-process cache (``SurveyResponse.definition``)."""
    return SurveyResponse.objects.select_related(
        "survey_version__survey", "administration__invitation"
    ).defer("survey_version__definition")


def _state(
    definition: dict,
    answers: dict,
    *,
    visible: list[VisibleQuestion] | None = None,
    questions: dict[str, dict] | None = None,
) -> dict:
    """visible / missing / progress from one walk of the definition."""
    if questions is None:
        questions = question_by_key(definition)
    if visible is None:
        visible = visible_questions(definition, answers, questions=questions)
    missing = missing_keys(definition, answers, visible=visible, questions=questions)
    return {
        "visible": [v.key for v in visible],
        "missing": missing,
        "progress": progress(
            definition, answers, visible=visible, missing=missing, questions=questions
        ),
    }


def _visible_set(definition: dict, answers: dict, questions: dict | None = None) -> set[str]:
    return {v.key for v in visible_questions(definition, answers, questions=questions)}


def _response_payload(
    response: SurveyResponse, *, answers: dict | None = None, state: dict | None = None
) -> dict:
    """The response summary; ``answers``/``state`` take a caller's precomputed
    answer map and ``_state`` so one request does not walk the definition twice."""
    if answers is None:
        answers = response.answer_map()
    data = ResponseSerializer(response).data
    data["answers"] = answers
    data.update(state if state is not None else _state(response.definition, answers))
    return data


class RunnerView(APIView):
    """Base for the participant-facing endpoints.

    These are deliberately unauthenticated: a survey is answered by whoever
    holds the link, and for an in-progress response the id *is* the credential
    (RUN-1). That has to be stated here rather than inherited from the
    project's DEFAULT_PERMISSION_CLASSES, because the app is installed into a
    host whose default is its own — PRomop's is IsAuthenticated, which turns
    every one of these into a 401. Authorization for a specific response is
    enforced per view, from the response id and the invitation, not by DRF.
    """

    permission_classes = [AllowAny]


class SurveyDefinitionView(RunnerView):
    throttle_classes = [ClientKeyThrottle]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request, slug: str):
        response = _response_for_definition(request, slug)
        if response is not None:
            survey, version = response.survey_version.survey, response.survey_version
            definition = response.definition
            lang = _language(request, definition, response.language)
        else:
            survey, version = _active_version(slug)
            definition = version.cached_definition
            # ``?invite=`` is ignored on an anonymous survey (it takes none);
            # elsewhere it is the credential for an account survey.
            invited = (
                takes_invitations(definition)
                and _administration(request, {}, survey=survey) is not None
            )
            _check_access(request, definition, invited=invited)
            lang = _language(request, definition)
        theme = theme_registry.resolve(survey.theme_code)
        theme_code = theme.code if theme else "default"
        etag = _etag(version, lang, theme_code)
        not_modified = get_conditional_response(request, etag=etag)
        if not_modified is not None:
            not_modified["ETag"] = etag
            return not_modified
        payload = dict(version.localized(lang))  # shared cache entry: copy before adding keys
        payload["theme_code"] = theme_code
        payload["translation_status"] = definition.get("translation_status", {})
        return Response(payload, headers={"ETag": etag, "Cache-Control": "private, max-age=60"})


# BCP 47-ish language tag: language, optional script or region subtag.
_LANG_TAG = re.compile(r"^([A-Za-z]{2,3})(?:-([A-Za-z]{2,4}))?$")


def _language_tag(raw: str) -> str:
    """Validate and normalise ``?lang=`` (``FR`` -> ``fr``, ``pt-br`` -> ``pt-BR``).

    Only a well-formed tag reaches gettext and the per-language option cache.
    """
    m = _LANG_TAG.match(raw)
    if m is None:
        raise ValidationError({"lang": "not a language tag"})
    lang, sub = m.group(1).lower(), m.group(2)
    if sub:
        lang += "-" + (sub.upper() if len(sub) == 2 else sub.title())
    return lang


class OptionsSourceView(RunnerView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, source: str):
        provider = iso3166.SOURCES.get(source)
        if provider is None:
            raise NotFound("unknown option source")
        lang = _language_tag(request.query_params.get("lang", "en"))
        return Response(
            {"source": source, "language": lang, "options": provider(lang)},
            headers={"Cache-Control": "public, max-age=86400"},
        )


class ResponseCreateView(RunnerView):
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
        definition = version.cached_definition
        if administration is not None and not takes_invitations(definition):
            # Linking would join anonymous answers to the invitation's email address.
            raise ValidationError(
                {"invitation": "this survey is anonymous and takes no invitation"}
            )
        _check_access(request, definition, invited=administration is not None)
        lang = data["language"]
        if lang not in definition["languages"]:
            raise ValidationError({"language": "not offered by this survey"})

        participant = (
            None if definition["participation"]["anonymous"] else resolve_participant(request)
        )
        if administration is not None:
            # An invitation link resumes its own administration's response and
            # nothing else: a logged-in participant's older in-progress response
            # (a previous administration) must not stand in for this one.
            existing = getattr(administration, "response", None)
            if existing is not None:
                return Response(_response_payload(existing), status=status.HTTP_200_OK)
        elif participant is not None and definition["participation"].get("resume") == "account":
            # Account resume (RUN-3): return the participant's in-progress response.
            # Serialise concurrent starts by the same participant so the
            # read-then-create below cannot produce two in-progress responses.
            SurveyVersion.objects.select_for_update().only("pk").get(pk=version.pk)
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
        consent = data.get("consent") or {}
        # Only an explicit agreement to the current notice is an attestation;
        # anything else is recorded nowhere (CON-1).
        agreed = bool(consent_cfg) and (
            consent.get("version") == consent_cfg["version"] and consent.get("agreed") is True
        )
        if consent_cfg and consent_cfg.get("required", True) and not agreed:
            raise ValidationError(
                {"consent": "agreement to the current consent notice is required"}
            )
        ua = request.META.get("HTTP_USER_AGENT", "")
        ua_hash = conf.salted_hash(ua) if ua else ""
        fields = {"survey_version": version, "language": lang, "user_agent_hash": ua_hash}
        if administration is not None:
            fields["administration"] = administration
            invited = getattr(administration.invitation, "participant_id", None)
            if invited is not None:
                fields["participant_id"] = invited
        elif participant is not None:
            fields["participant_id"] = participant
        minted = None
        if "participant_id" not in fields:
            # RUN-2: a response belongs to a participant even when nobody is
            # signed in. The host mints a record carrying nothing that could
            # name the respondent; unset, this is a no-op and the response is
            # created unbound as before.
            minted = mint_participant()
            if minted is not None:
                fields["participant_id"] = minted
        response = SurveyResponse.objects.create(**fields)
        if minted is not None:
            # So the host can tell a respondent from a patient in its own tables.
            MintedParticipant.objects.create(participant_id=minted)
        if agreed:
            text = pick(consent_cfg["text"], lang, definition["default_language"])
            SurveyConsent.objects.create(
                response=response,
                consent_version=consent_cfg["version"],
                text_hash=hashlib.sha256(text.encode()).hexdigest(),
                language=lang,
            )
        return Response(_response_payload(response), status=status.HTTP_201_CREATED)


class AnswerRejected(APIException):
    """400 with the engine's structured issues under ``value``, untouched.

    DRF's ValidationError would coerce every nested primitive to a string,
    losing the typed ``params`` the runner formats into its own language.
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid"

    def __init__(self, issues: list[dict]):
        super().__init__()
        self.detail = {"value": issues}


class ReadOnly(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "response is submitted and read-only"
    default_code = "read_only"


class SurveyClosed(APIException):
    status_code = status.HTTP_410_GONE
    default_detail = "survey is not open"
    default_code = "survey_closed"


class ResponseMixin:
    def get_response(self, response_id, *, lock: bool = False) -> SurveyResponse:
        qs = _responses()
        if lock:
            qs = qs.select_for_update(of=("self",))
        response = get_object_or_404(qs, pk=response_id)
        _owns(self.request, response)
        return response

    def writable(self, response_id, *, lock: bool = True) -> SurveyResponse:
        """Lock the response row for the transaction so concurrent writes and
        submit serialise (the status/answers read below stay consistent).
        ``lock=False`` is the same check outside a transaction, for work that
        must not hold the row (an out-of-process call) before the locked write.

        Writes stop once the survey leaves its effective window (410); the
        response stays readable so the runner can explain why.
        """
        response = self.get_response(response_id, lock=lock)
        if response.is_submitted:
            raise ReadOnly()
        error = response.survey_version.survey.closed_reason()
        if error:
            raise SurveyClosed(error)
        return response


class ResponseDetailView(ResponseMixin, RunnerView):
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
            key = data["last_question_key"]
            if key and key not in question_by_key(response.definition):
                raise ValidationError({"last_question_key": "not a question of this survey"})
            response.last_question_key = key
        response.save(update_fields=["language", "last_question_key", "updated_at"])
        # The runner merges only the fields it patched (language, last question);
        # answers/visibility are unchanged by a PATCH, so they are not recomputed.
        return Response(ResponseSerializer(response).data)


def _answer_result(
    definition: dict,
    question_key: str,
    value: dict,
    answers: dict,
    *,
    invalidated: list[str] | None = None,
    pruned: dict | None = None,
    visible: list[VisibleQuestion] | None = None,
    questions: dict[str, dict] | None = None,
) -> dict:
    return {
        "answer": {"key": question_key, "value": value},
        "invalidated": invalidated or [],
        "pruned": pruned or {},
        **_state(definition, answers, visible=visible, questions=questions),
    }


class AnswerView(ResponseMixin, RunnerView):
    # Per response *and* per client: the per-response bucket is fresh for every
    # (random) id, so on its own it would bound nothing.
    throttle_classes = [ResponseThrottle, WriteThrottle]

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
        visible = visible_questions(definition, answers, questions=questions)
        if not any(v.key == question_key for v in visible):
            raise AnswerRejected([issue("not_visible").as_dict()])
        if retained_when_hidden(question, answers.get(question_key)):
            # A recorded capture cannot be downgraded: the {provided: true} marker is
            # what makes the contact endpoint idempotent (one address per response).
            response.last_question_key = question_key
            response.save(update_fields=["last_question_key", "updated_at"])
            return Response(
                _answer_result(
                    definition,
                    question_key,
                    answers[question_key],
                    answers,
                    visible=visible,
                    questions=questions,
                )
            )
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
                questions=questions,
            )
        except AnswerError as exc:
            raise AnswerRejected(exc.as_list()) from exc
        answers[question_key] = value
        # One walk with the new answer: what is visible now, what no longer applies
        # (a hidden capture marker is retained by the engine, see cascade.py).
        cascade = apply_cascade(definition, answers, questions=questions)
        SurveyAnswer.objects.update_or_create(
            response=response,
            question_key=question_key,
            defaults={"value": value, "option_keys": option_keys_of(value)},
        )
        dead = [k for k in cascade.invalidated if k not in cascade.answers]
        if dead:
            SurveyAnswer.objects.filter(response=response, question_key__in=dead).delete()
        # A pruned matrix keeps its surviving rows; the client gets them back so
        # it never has to guess between "deleted" and "reduced".
        pruned = {k: cascade.answers[k] for k in cascade.invalidated if k in cascade.answers}
        for key, survivor in pruned.items():
            SurveyAnswer.objects.filter(response=response, question_key=key).update(
                value=survivor, option_keys=option_keys_of(survivor)
            )
        response.last_question_key = question_key
        response.save(update_fields=["last_question_key", "updated_at"])
        return Response(
            _answer_result(
                definition,
                question_key,
                value,
                cascade.answers,
                invalidated=cascade.invalidated,
                pruned=pruned,
                visible=cascade.visible_questions,
                questions=questions,
            )
        )


class SubmitView(ResponseMixin, RunnerView):
    throttle_classes = [ResponseThrottle, WriteThrottle]

    @transaction.atomic
    def post(self, request, response_id):
        response = self.writable(response_id)
        definition = response.definition
        answers = response.answer_map()
        state = _state(definition, answers)
        if state["missing"]:
            return Response({"missing": state["missing"]}, status=status.HTTP_400_BAD_REQUEST)
        response.status = ResponseStatus.SUBMITTED
        response.submitted_at = timezone.now()
        response.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(_response_payload(response, answers=answers, state=state))


_CAPTURE_KINDS = {"store_separately": "contact", "link_identity": "identity"}


def _capture_question(definition: dict, flag: str) -> dict:
    """The email question configured for the capture ``flag`` (CON-3/4), else 404."""
    for q in question_by_key(definition).values():
        if q["type"] == "email":
            if q["config"].get(flag):
                return q
            break
    raise NotFound(f"this survey has no {_CAPTURE_KINDS[flag]} capture")


def _mark_provided(response: SurveyResponse, key: str) -> None:
    """Record a completed capture; the marker is all the response ever holds."""
    SurveyAnswer.objects.update_or_create(
        response=response,
        question_key=key,
        defaults={"value": {"provided": True}, "option_keys": []},
    )


# The runner sends JSON, which only ever exists in ``request.data`` and frame
# locals: ``sensitive_post_parameters`` covers a form-encoded body
# (``request.POST``), ``sensitive_variables()`` masks every local in the view
# and the frames beneath it in Django's error reports, and the storage steps
# are wrapped so no exception carrying the address escapes as an unhandled 500.
@method_decorator(sensitive_post_parameters("email"), name="dispatch")
class ContactView(ResponseMixin, RunnerView):
    """Contact capture (CON-3): the address is stored with no link to the response.

    The address is kept out of error reports (CON-3/4) should anything raise.
    """

    # Per response *and* per client: an address is captured once per response, so
    # the capture budget bounds how many captures one caller can drive (its own
    # bucket, so captures never eat into a shared address's start budget).
    throttle_classes = [ResponseThrottle, CaptureThrottle]

    @sensitive_variables()
    @transaction.atomic
    def post(self, request, response_id):
        response = self.writable(response_id)
        ser = ContactSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        question = _capture_question(definition, "store_separately")
        answers = response.answer_map()
        if question["key"] not in _visible_set(definition, answers):
            raise ValidationError({"email": ["contact capture is not currently shown"]})
        if (answers.get(question["key"]) or {}).get("provided") is True:
            return Response(status=status.HTTP_204_NO_CONTENT)  # retry after a lost 204
        notice = pick(
            question.get("help", {}) or question["text"],
            response.language,
            definition["default_language"],
        )
        try:
            SurveyContact.objects.create(
                survey_version=response.survey_version,
                email=ser.validated_data["email"],
                language=response.language,
                consent_text=notice,
            )
            _mark_provided(response, question["key"])
        except Exception as exc:
            # An unhandled exception would carry the request body — the address —
            # into error reporting. Log the class only; the transaction rolls back.
            log.error(
                "contact capture failed with %s for response %s", type(exc).__name__, response.id
            )
            raise APIException("contact capture failed") from None
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(sensitive_post_parameters("email"), name="dispatch")
class IdentityView(ResponseMixin, RunnerView):
    """Identity capture (CON-4): the email goes to the host platform's identity service only."""

    # The per-client capture budget also caps how often a failing identity service
    # can be re-invoked: the per-response bucket alone is fresh for every id.
    throttle_classes = [ResponseThrottle, CaptureThrottle]

    @sensitive_variables()
    def post(self, request, response_id):
        # The checks and the host's service call run outside any transaction:
        # ``create_or_link`` is an out-of-process call of unknown latency, and
        # holding the response row lock (and the connection) across it would
        # queue every concurrent autosave for the response behind it. The
        # locked write below re-checks what it depends on; the idempotency key
        # makes a repeated service call harmless.
        response = self.writable(response_id, lock=False)
        if not conf.is_integrated():
            raise NotFound("identity capture is only available in the integrated profile")
        ser = ContactSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        definition = response.definition
        question = _capture_question(definition, "link_identity")
        if question["key"] not in _visible_set(definition, response.answer_map()):
            raise ValidationError({"email": ["identity capture is not currently shown"]})
        service = get_identity_service()
        if service is None:
            raise NotFound("no identity service is configured")
        result = None
        # Already linked: the marker answer makes a repeat harmless, and the
        # service must not be asked twice for the same response.
        if response.identity_linked_at is None:
            try:
                result = service.attach_account(
                    IdentityRequest(
                        email=ser.validated_data["email"],
                        idempotency_key=idempotency_key(response.id),
                        survey_slug=response.survey_version.survey.slug,
                        language=response.language,
                        participant_pk=response.participant_id_or_none,
                    )
                )
            except Exception as exc:
                # Any failure of the host's service (IdentityServiceError or a raw
                # transport/HTTP error it did not wrap) is a 503, never a 500: an
                # unhandled exception would carry the request body — the address —
                # into the host's error reporting. Log the class only.
                if not isinstance(exc, IdentityServiceError):
                    log.warning(
                        "identity service raised %s for response %s",
                        type(exc).__name__,
                        response.id,
                    )
                return Response(
                    {"detail": "identity service unavailable; you can still submit anonymously"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        with transaction.atomic():
            response = self.writable(response_id)
            if result is not None and response.identity_linked_at is None:
                if result.linked:
                    # The participant the response already had now has an
                    # account: promoted in place, so no answer moves.
                    response.identity_linked_at = timezone.now()
                    response.save(update_fields=["identity_linked_at", "updated_at"])
                    MintedParticipant.objects.filter(
                        participant_id=response.participant_id_or_none,
                        identified_at__isnull=True,
                    ).update(identified_at=response.identity_linked_at)
                elif result.conflicting_participant_pk is not None:
                    # The address belongs to somebody else (decision 7). Record
                    # the pair and attach nothing.
                    ParticipantMergeCandidate.objects.get_or_create(
                        minted_id=response.participant_id_or_none,
                        existing_id=result.conflicting_participant_pk,
                        resolved_at=None,
                    )
                    log.info(
                        "identity capture for response %s names another participant; "
                        "recorded a merge candidate and attached nothing",
                        response.id,
                    )
            # Either way the participant answered the question, and either way
            # they may submit (CON-7). They are told nothing about the conflict:
            # saying an address is already registered would leak that it is.
            _mark_provided(response, question["key"])
        return Response(status=status.HTTP_204_NO_CONTENT)
