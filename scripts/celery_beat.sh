#!/bin/sh

set -e

python manage.py wait_for_db

mkdir -p /app/celerybeat-data

echo "Starting Celery beat..."
exec celery -A notarios beat -l info --schedule /app/celerybeat-data/celerybeat-schedule
