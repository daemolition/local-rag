#!/bin/bash
set -e

echo "🚀 Local Document RAG - Docker"
echo "================================"

# Alembic Migration
echo "📊 Running database migrations..."
alembic upgrade head

# Admin-User existiert bereits durch Migration 002
echo "✅ Setup complete"
echo ""

exec "$@"
