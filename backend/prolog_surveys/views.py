from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, JsonResponse

from . import conf
from .models import LifecycleStatus, SurveyVersion
from .themes import registry

# Building the migration graph on every probe is wasteful; once a process has
# seen every migration applied that cannot change until it restarts.
_migrations_applied = False


def _migrations_pending() -> bool:
    global _migrations_applied
    if _migrations_applied:
        return False
    executor = MigrationExecutor(connection)
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        return True
    _migrations_applied = True
    return False


def health(request: HttpRequest) -> HttpResponse:
    """Liveness + readiness: database reachable, themes loaded, active surveys counted."""
    status = "ok"
    checks: dict[str, object] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - exercised only when the DB is down
        status = "error"
        checks["database"] = f"error: {exc.__class__.__name__}"
    else:
        if _migrations_pending():
            # Reachable but not ready: `manage.py migrate` has not run yet.
            status = "degraded"
            checks["migrations"] = "pending"
        else:
            checks["migrations"] = "applied"
            checks["active_surveys"] = SurveyVersion.objects.filter(
                status=LifecycleStatus.ACTIVE
            ).count()
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
