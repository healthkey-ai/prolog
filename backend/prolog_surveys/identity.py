"""Identity capture (CON-4): an email question gives a participant an account.

The response is already bound to a participant (RUN-2). The host's service is
asked to give *that* participant an account, so the person is promoted in place
and no answer moves. PROlog never stores the address — only that a link
happened, and, where the address turned out to belong to somebody else, the two
participant ids a human needs to reconcile them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from django.utils.module_loading import import_string

from . import conf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IdentityRequest:
    email: str
    idempotency_key: str
    survey_slug: str
    language: str
    # The participant the response is already bound to. The service gives *this*
    # record an account rather than returning one of its own choosing.
    participant_pk: Any


@dataclass(frozen=True)
class IdentityResult:
    """What the host did with the address.

    ``linked``: the participant in the request now has an account.

    Not linked, with ``conflicting_participant_pk`` set: the address already
    belongs to a different participant (open decision 7). Nothing is attached —
    joining two participant records is a clinical-safety decision, not a survey
    side effect — and the pair is recorded for a human to reconcile.
    """

    linked: bool
    conflicting_participant_pk: Any | None = None


class IdentityService(Protocol):
    def attach_account(self, request: IdentityRequest) -> IdentityResult: ...


class IdentityServiceError(Exception):
    """Raised by a service when the account cannot be created.

    Any other exception escaping ``attach_account`` is treated the same way
    (503, the participant stays unidentified); only its class name is logged.
    """


def get_identity_service() -> IdentityService | None:
    """The configured service: PROLOG_IDENTITY_SERVICE names a class, a
    factory function (both called with no arguments) or a prebuilt instance."""
    path = conf.get("PROLOG_IDENTITY_SERVICE")
    if not path:
        return None
    target = import_string(path)
    return target() if callable(target) else target


def idempotency_key(response_id: Any) -> str:
    return conf.salted_hash("identity", str(response_id))


def mint_participant() -> Any | None:
    """A participant record for a respondent nobody can name yet (RUN-2).

    The host's factory decides what that record is; in PRomop it is a `Person`
    with no identity and no demographics. Returns its pk, or None when no
    factory is configured — a deployment that has not opted in keeps creating
    responses with no participant, as it does today.
    """
    path = conf.get("PROLOG_PARTICIPANT_FACTORY")
    if not path:
        return None
    minted = import_string(path)()
    return getattr(minted, "pk", minted)


def host_facts(participant: Any, definition: dict[str, Any]) -> dict[str, str]:
    """The host's facts about ``participant`` for a survey that declares
    facts (DEF-14, RUN-23): only those declared, with a declared value. A
    provider that fails is logged and the response starts with every fact
    unknown; it never stops the participant from starting."""
    path = conf.get("PROLOG_FACTS_PROVIDER")
    if not path or not definition.get("facts"):
        return {}
    from .engine.facts import known_facts

    try:
        supplied = import_string(path)(participant, definition)
    except Exception:  # noqa: BLE001 - the host's code; the survey still starts
        logger.exception(
            "PROLOG_FACTS_PROVIDER failed for survey %s; starting with no facts", definition["slug"]
        )
        return {}
    return known_facts(definition, supplied if isinstance(supplied, dict) else {})


def revision_answers(
    participant: Any, definition: dict[str, Any], previous: dict[str, dict]
) -> dict[str, dict]:
    """The answers an update of a revisable survey starts from (RUN-4): the
    host's (PROLOG_REVISION_ANSWERS_PROVIDER), given the participant's last
    submitted answers, or those answers themselves. A provider that fails or
    returns something other than a dict is logged, and the update starts from
    the last submitted answers; it never stops the participant from starting.
    The caller checks every answer either way."""
    path = conf.get("PROLOG_REVISION_ANSWERS_PROVIDER")
    if not path:
        return previous
    try:
        supplied = import_string(path)(participant, definition, dict(previous))
    except Exception:  # noqa: BLE001 - the host's code; the update still starts
        logger.exception(
            "PROLOG_REVISION_ANSWERS_PROVIDER failed for survey %s; starting from the last answers",
            definition["slug"],
        )
        return previous
    if not isinstance(supplied, dict):
        logger.error(
            "PROLOG_REVISION_ANSWERS_PROVIDER returned %s for survey %s; starting from the last answers",
            type(supplied).__name__,
            definition["slug"],
        )
        return previous
    return {key: value for key, value in supplied.items() if isinstance(value, dict)}


def resolve_participant(request) -> Any | None:
    """Participant pk for an authenticated request (account surveys)."""
    path = conf.get("PROLOG_PARTICIPANT_RESOLVER")
    if path:
        return import_string(path)(request)
    from django.conf import settings

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if conf.participant_model() == settings.AUTH_USER_MODEL:
        return user.pk
    return None
