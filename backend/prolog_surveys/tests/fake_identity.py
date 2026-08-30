"""Fake identity service for tests (the host platform provides the real one)."""

from django.contrib.auth import get_user_model

from prolog_surveys.identity import IdentityRequest, IdentityResult, IdentityServiceError

CALLS: list[IdentityRequest] = []


class FakeIdentityService:
    def create_or_link(self, request: IdentityRequest) -> IdentityResult:
        CALLS.append(request)
        if request.email.endswith("@fail.example"):
            raise IdentityServiceError("upstream down")
        user, _ = get_user_model().objects.get_or_create(
            username=f"p-{request.idempotency_key[:12]}", defaults={"email": ""}
        )
        return IdentityResult(participant_pk=user.pk)
