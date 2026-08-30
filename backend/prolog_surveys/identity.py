"""Identity capture for anonymous surveys in the integrated profile (CON-4).

The host platform provides a service that turns a consented email into a
participant record; PROlog only ever stores the resulting participant link.
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


@dataclass(frozen=True)
class IdentityResult:
    participant_pk: Any


class IdentityService(Protocol):
    def create_or_link(self, request: IdentityRequest) -> IdentityResult: ...


class IdentityServiceError(Exception):
    """Raised by a service when the participant record cannot be created.

    Any other exception escaping ``create_or_link`` is treated the same way
    (503, response stays anonymous); only its class name is logged.
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
