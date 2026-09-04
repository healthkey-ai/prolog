"""Fake identity service for tests (the host platform provides the real one)."""

from django.contrib.auth import get_user_model

from prolog_surveys.identity import IdentityRequest, IdentityResult, IdentityServiceError

CALLS: list[IdentityRequest] = []

#: Addresses this fake treats as already belonging to somebody else. Maps the
#: address to the participant pk that owns it (open decision 7).
TAKEN: dict[str, object] = {}


class FakeIdentityService:
    def attach_account(self, request: IdentityRequest) -> IdentityResult:
        CALLS.append(request)
        if request.email.endswith("@fail.example"):
            raise IdentityServiceError("upstream down")
        if request.email.endswith("@crash.example"):
            raise RuntimeError("unwrapped transport error")
        if request.email in TAKEN:
            return IdentityResult(linked=False, conflicting_participant_pk=TAKEN[request.email])
        # The account is attached to the participant the caller already has.
        get_user_model().objects.filter(pk=request.participant_pk).update(
            username=f"identified-{request.idempotency_key[:12]}"
        )
        return IdentityResult(linked=True)
