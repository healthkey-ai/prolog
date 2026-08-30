"""Throttling without storing raw IPs (CON-6)."""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from .. import conf

# Used when the project's REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] does not
# name a scope (an integrated host that did not copy the standalone settings),
# so a missing rate degrades to these defaults instead of a 500 on every call.
DEFAULT_RATES = {"run.read": "1200/hour", "run.create": "30/hour", "run.answer": "600/hour"}


def client_address(request) -> str:
    """The caller's address, trusting X-Forwarded-For only for the configured
    number of proxies (anything a client can set itself would let it pick a
    fresh throttle bucket per request).

    Same rule as DRF's ``SimpleRateThrottle.get_ident`` with ``NUM_PROXIES``:
    a chain shorter than the configured proxy count yields its outermost hop
    (still one bucket per client), never the proxy's own address (which would
    put every client behind it into a single bucket)."""
    proxies = int(conf.get("PROLOG_NUM_PROXIES") or 0)
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies > 0 and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-min(proxies, len(hops))]
    return request.META.get("REMOTE_ADDR", "")


def client_key(request) -> str:
    """Salted hash of the caller's address; never persisted."""
    return conf.salted_hash(client_address(request))


class _RunnerThrottle(SimpleRateThrottle):
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope) or DEFAULT_RATES[self.scope]


class ClientKeyThrottle(_RunnerThrottle):
    scope = "run.read"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_key(request)}


class CreateThrottle(ClientKeyThrottle):
    scope = "run.create"


class ResponseThrottle(_RunnerThrottle):
    """Per response id, for the autosave endpoint."""

    scope = "run.answer"

    def get_cache_key(self, request, view):
        ident = view.kwargs.get("response_id") or client_key(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
