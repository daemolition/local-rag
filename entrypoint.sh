#!/bin/bash
set -e

echo "Local Document RAG - Docker"
echo "================================"

# Alembic Migration
echo "Running database migrations..."
alembic upgrade head

echo "Setup complete"
echo ""

exec "$@"
