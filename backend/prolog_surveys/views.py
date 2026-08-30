from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse

from . import conf
from .models import LifecycleStatus, SurveyVersion
from .themes import registry


def health(request: HttpRequest) -> HttpResponse:
    """Liveness + readiness: database reachable, themes loaded, active surveys counted."""
    status = "ok"
    checks: dict[str, object] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
        checks["active_surveys"] = SurveyVersion.objects.filter(
            status=LifecycleStatus.ACTIVE
        ).count()
    except Exception as exc:  # pragma: no cover - exercised only when the DB is down
        status = "error"
        checks["database"] = f"error: {exc.__class__.__name__}"
    themes = registry.all()
    checks["themes"] = sorted(themes)
    if "default" not in themes:
        status = "degraded"
    code = 200 if status == "ok" else 503
    return JsonResponse(
        {"service": "PROlog", "status": status, "profile": conf.profile(), "checks": checks},
        status=code,
    )


def runner_index(request: HttpRequest) -> HttpResponse:
    index = settings.RUNNER_DIST / "index.html"
    if not index.exists():
        raise Http404("Runner is not built")
    return FileResponse(open(index, "rb"), content_type="text/html")
