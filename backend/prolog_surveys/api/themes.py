"""Theme API (THM-2)."""

from __future__ import annotations

import mimetypes

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

        def asset_url(relative: str) -> str:
            return request.build_absolute_uri(
                reverse("run-theme-asset", kwargs={"code": code, "path": relative})
            )

        doc = theme.public(asset_url)
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
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        if file.suffix == ".woff2":
            content_type = "font/woff2"
        response = FileResponse(open(file, "rb"), content_type=content_type)
        response["Cache-Control"] = f"public, max-age={ASSET_MAX_AGE}, immutable"
        response["Access-Control-Allow-Origin"] = "*"
        return response
