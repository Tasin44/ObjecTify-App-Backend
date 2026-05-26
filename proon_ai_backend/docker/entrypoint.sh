#!/bin/sh
set -e

if [ "$ENVIRONMENT" = "server" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput

  if [ "$RUN_SEED_DATA" = "true" ]; then
    python manage.py seed_data
  fi
fi

exec "$@"
