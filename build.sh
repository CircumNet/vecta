#!/usr/bin/env bash
# Exit on error
set -o errexit

pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Run database migrations
python manage.py migrate

# Create cache table
python manage.py createcachetable

# Create superuser if it doesn't exist
python manage.py ensure_superuser

# ONLY SEED IF THE ENVIRONMENT VARIABLE IS SET
if [ "$SEED_DB" = "1" ]; then
    echo "Seeding the database with demo data..."
    python manage.py seed_demo --with-requests
fi
