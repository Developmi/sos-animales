#!/bin/sh
set -e

# Run database migrations automatically
echo "Applying database migrations with Alembic..."
alembic upgrade head

# Seed Colombian geographic divisions (departments & municipalities) and initial fixtures if empty
echo "Ensuring Colombian geographic data is loaded..."
python -m seed

# Hand off execution to the container CMD
exec "$@"
