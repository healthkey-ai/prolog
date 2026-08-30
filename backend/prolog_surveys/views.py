from django.conf import settings
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse

from . import conf


def health(request: HttpRequest) -> HttpResponse:
    return JsonResponse({"service": "PROlog", "status": "ok", "profile": conf.profile()})


def runner_index(request: HttpRequest) -> HttpResponse:
    index = settings.RUNNER_DIST / "index.html"
    if not index.exists():
        raise Http404("Runner is not built")
    return FileResponse(open(index, "rb"), content_type="text/html")
