"""Throttling without storing raw IPs (CON-6).

Buckets are keyed by a salted hash of the caller's address, never the address
itself. The address comes from DRF's ``get_ident`` — X-Forwarded-For is trusted
only for ``REST_FRAMEWORK["NUM_PROXIES"]`` hops (wired from PROLOG_NUM_PROXIES in
the standalone settings), since anything a client can set itself would let it
pick a fresh bucket per request. Counters live in Django's default cache; see
docs/deployment.md for what that means across worker processes.
"""

from __future__ import annotations

from rest_framework.throttling import SimpleRateThrottle

from .. import conf


class _RunnerThrottle(SimpleRateThrottle):
    def get_rate(self):
        return self.THROTTLE_RATES.get(self.scope) or conf.THROTTLE_RATES[self.scope]


class ClientKeyThrottle(_RunnerThrottle):
    scope = "run.read"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": conf.salted_hash(self.get_ident(request)),
        }


class CreateThrottle(ClientKeyThrottle):
    """Response creation per client."""

    scope = "run.create"


class CaptureThrottle(ClientKeyThrottle):
    """Contact/identity capture per client: its own bucket, so captures never
    consume a shared address's response-creation budget (and vice versa)."""

    scope = "run.capture"


class WriteThrottle(ClientKeyThrottle):
    """Answer/submit per client: the per-response bucket alone is fresh for
    every id, so a stream of writes to random ids would never be bounded."""

    scope = "run.write"


class ResponseThrottle(_RunnerThrottle):
    """Per response id, for the autosave endpoint.

    The id is the capability token (RUN-1): it is hashed like a client address
    before it becomes a key in the (possibly shared) cache.
    """

    scope = "run.answer"

    def get_cache_key(self, request, view):
        ident = str(view.kwargs.get("response_id") or self.get_ident(request))
        return self.cache_format % {"scope": self.scope, "ident": conf.salted_hash(ident)}
