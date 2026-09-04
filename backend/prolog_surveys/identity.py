"""Identity capture (CON-4): an email question gives a participant an account.

The response is already bound to a participant (RUN-2). The host's service is
asked to give *that* participant an account, so the person is promoted in place
and no answer moves. PROlog never stores the address — only that a link
happened, and, where the address turned out to belong to somebody else, the two
participant ids a human needs to reconcile them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from django.utils.module_loading import import_string

from . import conf


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
