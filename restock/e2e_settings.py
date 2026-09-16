"""Isolated settings used exclusively by the browser acceptance suite."""

from .settings import *  # noqa: F403


DEBUG = True
DATABASES["default"] = {  # noqa: F405
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / ".e2e.sqlite3",  # noqa: F405
}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "console-e2e",
    },
}
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"
CONSOLE_CATALOG_OBSERVER = "monitor.e2e.observe_product"
CONSOLE_CHANNEL_SENDER = "monitor.e2e.send_channel"
