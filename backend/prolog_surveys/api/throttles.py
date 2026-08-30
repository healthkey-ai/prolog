"""Throttling without storing raw IPs (CON-6)."""

from __future__ import annotations

import hashlib

from rest_framework.throttling import SimpleRateThrottle

from .. import conf


def client_key(request) -> str:
    """Salted hash of the caller's address and user agent; never persisted."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    addr = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    ua = request.META.get("HTTP_USER_AGENT", "")
    raw = f"{conf.get('PROLOG_CLIENT_KEY_SALT')}|{addr}|{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()


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
