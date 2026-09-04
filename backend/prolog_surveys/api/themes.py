"""Theme API (THM-2)."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.cache import get_conditional_response
from rest_framework.response import Response

from ..themes import registry
from .throttles import ClientKeyThrottle
from .views import RunnerView

# Asset URLs in the theme document carry ``?v=<content hash>``; only that URL
# may be cached without revalidation (THM-7: replacing a logo or font file and
# reloading the registry publishes it under a new URL, no rename needed). The
# bare or stale URL revalidates with the same hash as its ETag.
ASSET_MAX_AGE = 60 * 60 * 24 * 365
UNVERSIONED_ASSET_MAX_AGE = 300


@lru_cache(maxsize=256)
def _digest(file: str, mtime_ns: int, size: int) -> str:
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()[:16]


def asset_version(file: Path) -> str:
    """Short content hash of an asset file, recomputed when the file changes."""
    st = file.stat()
    return _digest(str(file), st.st_mtime_ns, st.st_size)


class ThemeView(RunnerView):
    throttle_classes = [ClientKeyThrottle]

    def get(self, request, code: str):
        theme = registry.get(code)
        if theme is None:
            raise Http404("unknown theme")

        # Asset paths (and their content versions) are resolved once per theme;
        # only the scheme and host (which belong to this request) are added here.
        def asset_url(relative: str) -> str:
            url = reverse("run-theme-asset", kwargs={"code": code, "path": relative})
            file = theme.asset_path(relative)
            return url if file is None else f"{url}?v={asset_version(file)}"

        doc = theme.public(asset_url, request.build_absolute_uri)
        doc["warnings"] = theme.warnings
        return Response(doc, headers={"Cache-Control": "public, max-age=300"})


class ThemeAssetView(RunnerView):
    throttle_classes: list = []

    def get(self, request, code: str, path: str):
        theme = registry.get(code)
        if theme is None:
            raise Http404("unknown theme")
        file = theme.asset_path(path)
        if file is None:
            raise Http404("unknown asset")
        version = asset_version(file)
        etag = f'"{version}"'
        response = get_conditional_response(request, etag=etag)
        if response is None:
            # FileResponse guesses the content type from the name (mimetypes knows
            # every extension in ASSET_EXTENSIONS, woff2 included) and sets the length.
            response = FileResponse(open(file, "rb"))
        response["ETag"] = etag
        if request.query_params.get("v") == version:
            response["Cache-Control"] = f"public, max-age={ASSET_MAX_AGE}, immutable"
        else:
            response["Cache-Control"] = f"public, max-age={UNVERSIONED_ASSET_MAX_AGE}"
        response["Access-Control-Allow-Origin"] = "*"
        return response
