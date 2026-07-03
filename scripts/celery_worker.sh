#!/bin/sh

set -e

python manage.py wait_for_db

if [ "$ENVIRONMENT" = "development" ]; then
  echo "Starting Celery worker with autoreload (development)..."
  exec watchmedo auto-restart \
    --directory=/app \
    --pattern='*.py' \
    --recursive \
    -- celery -A notarios worker -l info
fi

echo "Starting Celery worker..."
exec celery -A notarios worker -l info
