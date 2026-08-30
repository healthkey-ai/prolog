from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from prolog_surveys.views import runner_index

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("prolog_surveys.urls")),
]

if settings.RUNNER_DIST.exists():
    # Serve the built runner for every non-API route (client-side routing).
    urlpatterns.append(re_path(r"^(?!api/|admin/|static/).*$", runner_index, name="runner"))
