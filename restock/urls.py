from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from monitor.console.session_api import console_shell


def healthz(_request):
    return JsonResponse({"ok": True})


urlpatterns = [
    path("healthz", healthz),
    path("api/console/v1/", include("monitor.console.urls")),
    path("console/", console_shell, name="console"),
    path("console/<path:route>", console_shell),
    path("admin/", admin.site.urls),
]
