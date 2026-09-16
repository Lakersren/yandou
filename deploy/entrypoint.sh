#!/bin/sh
set -eu

case "${1:-web}" in
  web)
    python manage.py migrate --noinput
    python manage.py seed_sites
    python manage.py seed_roles
    python manage.py create_admin
    python manage.py collectstatic --noinput
    exec gunicorn restock.wsgi:application --bind 0.0.0.0:8000 --workers "${WEB_WORKERS:-1}" --timeout 60
    ;;
  worker)
    exec celery -A restock worker -l INFO \
      --concurrency "${WORKER_CONCURRENCY:-1}" \
      --queues "${WORKER_QUEUES:-celery}" \
      --prefetch-multiplier "${WORKER_PREFETCH_MULTIPLIER:-1}"
    ;;
  beat)
    exec celery -A restock beat -l INFO --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
