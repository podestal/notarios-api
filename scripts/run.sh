#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Wait for the database to be ready before continuing.
python manage.py wait_for_db

# Collect static files (CSS, JS, etc.) without prompting for input.
# python manage.py collectstatic --noinput

# Apply any pending database migrations.
# python manage.py migrate


if [ "$ENVIRONMENT" = "development" ]; then
    echo "Starting server with Dev server for development..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting server with Gunicorn ..."
    exec gunicorn notarios.wsgi:application \
        --workers 4 \
        --bind 0.0.0.0:8000 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        --capture-output
fi



