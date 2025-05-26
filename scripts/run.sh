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
    # echo "Starting server with Daphne for development..."
    echo "Starting server with Dev server for development..."
    # exec daphne -b 0.0.0.0 -p 8000 notarios.asgi:application
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting server with Daphne for testing..."
    # exec gunicorn notarios.wsgi:application --bind 0.0.0.0:8000 --timeout=5 --threads=10
    exec daphne -b 0.0.0.0 -p 8000 notarios.asgi:application
fi



