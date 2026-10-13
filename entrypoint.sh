#!/bin/bash
set -e

echo "Open Knowledge UI - Docker"
echo "================================"

# Alembic Migration
echo "Running database migrations..."
alembic upgrade head

echo "Setup complete"
echo ""

exec "$@"
