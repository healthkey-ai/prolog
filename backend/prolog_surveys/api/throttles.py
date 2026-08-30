"""Throttling without storing raw IPs (CON-6)."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from .. import conf


def client_address(request) -> str:
    """The caller's address, trusting X-Forwarded-For only for the configured
    number of proxies (anything a client can set itself would let it pick a
    fresh throttle bucket per request)."""
    proxies = int(conf.get("PROLOG_NUM_PROXIES") or 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies > 0 and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= proxies:
            return hops[-proxies]
    return request.META.get("REMOTE_ADDR", "")


def client_key(request) -> str:
    """Salted hash of the caller's address; never persisted."""
    return conf.salted_hash(client_address(request))


class ClientKeyThrottle(SimpleRateThrottle):
    scope = "run.read"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_key(request)}


class CreateThrottle(ClientKeyThrottle):
    scope = "run.create"


class ResponseThrottle(SimpleRateThrottle):
    """Per response id, for the autosave endpoint."""

    scope = "run.answer"

    def get_cache_key(self, request, view):
        ident = view.kwargs.get("response_id") or client_key(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
