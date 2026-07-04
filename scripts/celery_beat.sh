#!/bin/sh

set -e

python manage.py wait_for_db

echo "Starting Celery beat..."
exec celery -A notarios beat -l info
