"""Theme API (THM-2)."""

from __future__ import annotations

from django.http import FileResponse, Http404
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.views import APIView

from ..themes import registry
from .throttles import ClientKeyThrottle

ASSET_MAX_AGE = 60 * 60 * 24 * 365


class ThemeView(APIView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, code: str):
        theme = registry.get(code)
        if theme is None:
            raise Http404("unknown theme")
        # Asset paths are resolved once per theme; only the scheme and host
        # (which belong to this request) are added here.
        doc = theme.public(
            lambda relative: reverse("run-theme-asset", kwargs={"code": code, "path": relative}),
            request.build_absolute_uri,
        )
        doc["warnings"] = theme.warnings
        return Response(doc, headers={"Cache-Control": "public, max-age=300"})


class ThemeAssetView(APIView):
    throttle_classes: list = []

    def get(self, request, code: str, path: str):
        theme = registry.get(code)
        if theme is None:
            raise Http404("unknown theme")
        file = theme.asset_path(path)
        if file is None:
            raise Http404("unknown asset")
        # FileResponse guesses the content type from the name (mimetypes knows
        # every extension in ASSET_EXTENSIONS, woff2 included) and sets the length.
        response = FileResponse(open(file, "rb"))
        response["Cache-Control"] = f"public, max-age={ASSET_MAX_AGE}, immutable"
        response["Access-Control-Allow-Origin"] = "*"
        return response
