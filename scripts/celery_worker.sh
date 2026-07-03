#!/bin/sh

set -e

python manage.py wait_for_db

exec celery -A notarios worker -l info
